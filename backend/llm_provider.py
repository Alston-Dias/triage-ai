"""
Pluggable LLM provider abstraction.

Default behaviour (May 2026): every AI call routes through the OpenAI-compatible
gateway configured at the repo root via `.env`:

    MODEL=gpt-5.2-CIO
    GATEWAY_BASE_URL=https://<host>/v1
    GATEWAY_API_KEY=sk-...

`get_chat()` returns an object whose `.send_message(UserMessage)` is awaitable
and returns the assistant text — same shape as
`emergentintegrations.llm.chat.LlmChat`, so existing call sites work unchanged.

A legacy `emergent` provider (Claude via emergentintegrations) and a generic
`openai` provider (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL) are still selectable
via LLM_PROVIDER for fallback / parity with older deployments.

Optional extras for the gateway:
    LLM_TIMEOUT_SECONDS=90
    LLM_EXTRA_HEADER_<NAME>=value          # each var becomes an HTTP header
    EMBEDDINGS_MODEL=embeddings            # used by get_embeddings()
"""
from __future__ import annotations

import os
import logging
from typing import Any, List, Optional, Sequence

import httpx

logger = logging.getLogger(__name__)

# --- Try to import emergentintegrations (legacy provider) -------------------
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
    _HAS_EMERGENT = True
except Exception:  # pragma: no cover - only matters in stripped builds
    _HAS_EMERGENT = False

    class UserMessage:  # minimal stand-in
        def __init__(self, text: str):
            self.text = text


# ----------------------------------------------------------------------------
# Gateway helpers
# ----------------------------------------------------------------------------
def _gateway_base_url() -> str:
    """First-class gateway URL, with legacy LLM_BASE_URL fallback."""
    url = (
        os.environ.get("GATEWAY_BASE_URL")
        or os.environ.get("LLM_BASE_URL")
        or ""
    ).strip()
    return url.rstrip("/")


def _gateway_api_key() -> str:
    return (
        os.environ.get("GATEWAY_API_KEY")
        or os.environ.get("LLM_API_KEY")
        or ""
    ).strip()


def _gateway_model() -> str:
    """Resolved chat model for the gateway."""
    return (
        os.environ.get("MODEL")
        or os.environ.get("LLM_MODEL")
        or "gpt-5.2-CIO"
    ).strip()


def _gateway_embeddings_model() -> str:
    return (
        os.environ.get("EMBEDDINGS_MODEL")
        or os.environ.get("LLM_EMBEDDINGS_MODEL")
        or "embeddings"
    ).strip()


def _gateway_configured() -> bool:
    return bool(_gateway_base_url() and _gateway_api_key())


def _resolve_provider() -> str:
    """
    Pick the provider in this order:
      1. Explicit LLM_PROVIDER env var, if set
      2. "gateway" when GATEWAY_BASE_URL+GATEWAY_API_KEY are present
      3. "emergent" when EMERGENT_LLM_KEY is present
      4. "gateway" (will raise a clear error at call-time if not configured)
    """
    raw = (os.environ.get("LLM_PROVIDER") or "").lower().strip()
    if raw:
        return raw
    if _gateway_configured():
        return "gateway"
    if (os.environ.get("EMERGENT_LLM_KEY") or "").strip():
        return "emergent"
    return "gateway"


def _collect_extra_headers() -> dict:
    """
    Any env var named LLM_EXTRA_HEADER_<NAME>=value becomes an HTTP header
    'NAME: value'. Lets ops add e.g. a tenant id without code changes.
    """
    extras: dict = {}
    prefix = "LLM_EXTRA_HEADER_"
    for k, v in os.environ.items():
        if k.startswith(prefix) and v:
            header_name = k[len(prefix):].replace("_", "-")
            extras[header_name] = v
    return extras


# ----------------------------------------------------------------------------
# OpenAI-compatible chat session
# ----------------------------------------------------------------------------
class _OpenAICompatChat:
    """
    Thin in-memory chat session that posts to an OpenAI-compatible
    `/chat/completions` endpoint. Same interface as LlmChat so call sites
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

    # Match LlmChat's fluent API. When the gateway is in use we intentionally
    # IGNORE model_hint — there is exactly one MODEL per deployment, so call
    # sites that pass `model_hint="anthropic:claude-..."` keep working but no
    # longer override the configured gateway model.
    def with_model(self, *args: Any, **kwargs: Any) -> "_OpenAICompatChat":
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
                    f"LLM gateway returned {resp.status_code}: {body}"
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

    Provider selection comes from _resolve_provider():
      - "gateway" (default) → OpenAI-compatible call to GATEWAY_BASE_URL using
        MODEL + GATEWAY_API_KEY. `model_hint` is ignored on purpose.
      - "openai" | "openai_compatible" | "custom" | "ibm_bob" → same code path
        but reading the legacy LLM_BASE_URL / LLM_API_KEY / LLM_MODEL vars.
      - "emergent" → legacy Claude path via emergentintegrations and
        EMERGENT_LLM_KEY. `model_hint="anthropic:<model>"` selects the model.
    """
    provider = _resolve_provider()
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "90"))

    if provider in {"gateway", "openai", "openai_compatible", "custom", "ibm_bob", "bob"}:
        base_url = _gateway_base_url() or "https://api.openai.com/v1"
        api_key = _gateway_api_key()
        model = _gateway_model()
        if not api_key:
            raise RuntimeError(
                "LLM gateway is not configured. Set GATEWAY_BASE_URL + GATEWAY_API_KEY "
                "(and MODEL) in the repo-root .env, or switch LLM_PROVIDER=emergent "
                "and set EMERGENT_LLM_KEY."
            )
        return _OpenAICompatChat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_message=system_message,
            session_id=session_id,
            timeout=timeout,
            extra_headers=_collect_extra_headers(),
        )

    # ---- legacy: emergent ----
    if not _HAS_EMERGENT:
        raise RuntimeError(
            "emergentintegrations is not installed and no LLM gateway is configured."
        )
    key = (os.environ.get("EMERGENT_LLM_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "EMERGENT_LLM_KEY is empty and LLM_PROVIDER=emergent. "
            "Either set EMERGENT_LLM_KEY or remove LLM_PROVIDER to fall back to the gateway."
        )
    chat = LlmChat(api_key=key, session_id=session_id, system_message=system_message)
    if model_hint and ":" in model_hint:
        provider_name, model_name = model_hint.split(":", 1)
        chat = chat.with_model(provider_name.strip(), model_name.strip())
    return chat


def llm_is_configured() -> bool:
    """Lightweight check used by call sites that want to fall back gracefully."""
    provider = _resolve_provider()
    if provider == "emergent":
        return bool((os.environ.get("EMERGENT_LLM_KEY") or "").strip())
    return _gateway_configured()


def active_model() -> str:
    """Convenience for logs / UI banners."""
    if _resolve_provider() == "emergent":
        return "emergent:claude-sonnet-4-5"
    return _gateway_model()


# ----------------------------------------------------------------------------
# Embeddings (optional, gateway only)
# ----------------------------------------------------------------------------
async def get_embeddings(
    texts: Sequence[str],
    *,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> List[List[float]]:
    """
    Generate embeddings via the gateway's OpenAI-compatible /embeddings
    endpoint. Returns one float vector per input string.

    Raises RuntimeError if the gateway is not configured or the response
    shape is unexpected. Currently nothing in the app calls this — it is
    provided so future features (semantic search, dedupe, etc.) can plug in.
    """
    if not _gateway_configured():
        raise RuntimeError(
            "Embeddings require GATEWAY_BASE_URL + GATEWAY_API_KEY to be set."
        )
    inputs = [t for t in texts if t is not None]
    if not inputs:
        return []

    url = f"{_gateway_base_url()}/embeddings"
    headers = {
        "Authorization": f"Bearer {_gateway_api_key()}",
        "Content-Type": "application/json",
    }
    headers.update(_collect_extra_headers())
    payload = {
        "model": (model or _gateway_embeddings_model()),
        "input": inputs,
    }
    request_timeout = timeout if timeout is not None else float(
        os.environ.get("LLM_TIMEOUT_SECONDS", "90")
    )

    async with httpx.AsyncClient(timeout=request_timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Embeddings endpoint returned {resp.status_code}: {resp.text[:400]}"
            )
        data = resp.json() or {}

    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected embeddings response shape: {data!r}")
    return [item.get("embedding", []) for item in items]


__all__ = [
    "get_chat",
    "get_embeddings",
    "llm_is_configured",
    "active_model",
    "UserMessage",
]
