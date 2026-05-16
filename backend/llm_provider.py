"""
Pluggable LLM provider abstraction.

By default this preserves the existing behaviour (emergentintegrations + Claude
Sonnet 4.5 via EMERGENT_LLM_KEY) so nothing changes for local dev.

To switch to ANY other LLM that exposes an OpenAI-compatible
`/chat/completions` endpoint (OpenAI, Azure OpenAI, OpenRouter, watsonx via
its OpenAI-compat layer, vLLM, Ollama, LocalAI, IBM "Bob", etc.), set:

    LLM_PROVIDER=openai
    LLM_BASE_URL=https://your-endpoint/v1
    LLM_API_KEY=sk-...
    LLM_MODEL=ibm/granite-3-8b-instruct        # or whatever the provider expects

Optional:
    LLM_TIMEOUT_SECONDS=90
    LLM_EXTRA_HEADER_<NAME>=value              # add custom headers (each var becomes
                                               # an HTTP header named <NAME>)

The factory `get_chat()` returns an object whose `.send_message(UserMessage)` is
awaitable and returns the assistant text — the same shape as
`emergentintegrations.llm.chat.LlmChat`, so existing call sites just swap one
line.
"""
from __future__ import annotations

import os
import logging
from typing import Any, List, Optional

import httpx

logger = logging.getLogger(__name__)

# --- Try to import emergentintegrations (still the default) -----------------
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
    _HAS_EMERGENT = True
except Exception:  # pragma: no cover - only matters in stripped builds
    _HAS_EMERGENT = False

    class UserMessage:  # minimal stand-in
        def __init__(self, text: str):
            self.text = text


# ----------------------------------------------------------------------------
# OpenAI-compatible chat session
# ----------------------------------------------------------------------------
class _OpenAICompatChat:
    """
    Thin in-memory chat session that posts to an OpenAI-compatible
    `/chat/completions` endpoint. Keeps the same interface as LlmChat so we
    can swap providers transparently.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        system_message: str,
        session_id: str,
        timeout: float = 90.0,
        extra_headers: Optional[dict] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.system_message = system_message
        self.session_id = session_id
        self.timeout = timeout
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        self._headers = headers
        self._history: List[dict] = []

    # Match LlmChat's fluent API. Accepts (provider, model) but we only care
    # about model here -- provider is implicit in the configured base_url.
    def with_model(self, *args: Any, **kwargs: Any) -> "_OpenAICompatChat":
        if len(args) >= 2 and args[1]:
            self.model = str(args[1])
        elif "model" in kwargs and kwargs["model"]:
            self.model = str(kwargs["model"])
        return self

    async def send_message(self, msg: Any) -> str:
        text = getattr(msg, "text", None) or str(msg)
        self._history.append({"role": "user", "content": text})

        messages: List[dict] = []
        if self.system_message:
            messages.append({"role": "system", "content": self.system_message})
        messages.extend(self._history)

        url = f"{self.base_url}/chat/completions"
        payload = {"model": self.model, "messages": messages}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=self._headers, json=payload)
            if resp.status_code >= 400:
                body = resp.text[:500]
                raise RuntimeError(
                    f"LLM provider returned {resp.status_code}: {body}"
                )
            data = resp.json()

        try:
            reply = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(
                f"Unexpected LLM response shape from {url}: {data!r}"
            ) from e

        self._history.append({"role": "assistant", "content": reply})
        return reply


def _collect_extra_headers() -> dict:
    """
    Any env var named LLM_EXTRA_HEADER_<NAME>=value becomes an HTTP header
    'NAME: value'. Lets users add e.g. an IBM watsonx project id, a tenant
    id, or a `X-Bob-Tenant` header without code changes.
    """
    extras: dict = {}
    prefix = "LLM_EXTRA_HEADER_"
    for k, v in os.environ.items():
        if k.startswith(prefix) and v:
            header_name = k[len(prefix):].replace("_", "-")
            extras[header_name] = v
    return extras


# ----------------------------------------------------------------------------
# Factory
# ----------------------------------------------------------------------------
def get_chat(
    *,
    session_id: str,
    system_message: str,
    model_hint: Optional[str] = None,
) -> Any:
    """
    Returns a chat object compatible with the LlmChat interface
    (.send_message(UserMessage) -> str).

    Provider selection comes from LLM_PROVIDER env var:
      - "emergent" (default) → emergentintegrations + Claude (uses
        EMERGENT_LLM_KEY). `model_hint` of the form "anthropic:model-name"
        controls the model.
      - "openai" | "openai_compatible" | "custom" | "ibm_bob" → any provider
        exposing an OpenAI-compatible /chat/completions endpoint, controlled
        by LLM_BASE_URL / LLM_API_KEY / LLM_MODEL.
    """
    provider = (os.environ.get("LLM_PROVIDER") or "emergent").lower().strip()
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "90"))

    if provider in {"openai", "openai_compatible", "custom", "ibm_bob", "bob"}:
        base_url = (os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1").strip()
        api_key = (os.environ.get("LLM_API_KEY") or "").strip()
        model = (os.environ.get("LLM_MODEL") or "gpt-4o-mini").strip()
        if not api_key:
            raise RuntimeError(
                "LLM_PROVIDER is set to a non-emergent provider but LLM_API_KEY is empty. "
                "Set LLM_API_KEY in the environment, or switch LLM_PROVIDER=emergent."
            )
        chat = _OpenAICompatChat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_message=system_message,
            session_id=session_id,
            timeout=timeout,
            extra_headers=_collect_extra_headers(),
        )
        # `model_hint` like "anthropic:claude-sonnet-4-5-..." is ignored for
        # custom providers -- the model is decided by LLM_MODEL.
        return chat

    # ---- default: emergent ----
    if not _HAS_EMERGENT:
        raise RuntimeError(
            "emergentintegrations is not installed and LLM_PROVIDER is not 'openai'."
        )
    key = (os.environ.get("EMERGENT_LLM_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "EMERGENT_LLM_KEY is empty. Either set EMERGENT_LLM_KEY in backend/.env "
            "or switch to a custom provider with LLM_PROVIDER=openai."
        )
    chat = LlmChat(api_key=key, session_id=session_id, system_message=system_message)
    if model_hint and ":" in model_hint:
        provider_name, model_name = model_hint.split(":", 1)
        chat = chat.with_model(provider_name.strip(), model_name.strip())
    return chat


def llm_is_configured() -> bool:
    """Lightweight check used by call sites that want to fall back gracefully."""
    provider = (os.environ.get("LLM_PROVIDER") or "emergent").lower().strip()
    if provider == "emergent":
        return bool((os.environ.get("EMERGENT_LLM_KEY") or "").strip())
    return bool((os.environ.get("LLM_API_KEY") or "").strip())


__all__ = ["get_chat", "llm_is_configured", "UserMessage"]
