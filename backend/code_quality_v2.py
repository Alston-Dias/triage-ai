"""
Code Quality v2 — user-driven code scans + external scanner integrations.

All endpoints are mounted under /api/code-quality/* by server.py.

Sources of scans:
  - github        : clone a public or private GitHub repo, analyze with Claude
  - upload        : analyze an uploaded .zip
  - integration   : pull issues from an external scanner (SonarQube, SonarCloud,
                    Snyk, GitHub Advanced Security, Semgrep Cloud, or Custom)

Mongo collections:
  - cq_scans         : scan rows (status, totals, source metadata)
  - cq_issues        : flattened issues belonging to scans
  - cq_integrations  : per-user external scanner credentials
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel, Field

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("triageai.code_quality_v2")

# ----------------------------- Config -----------------------------
CODE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".php",
    ".c", ".cc", ".cpp", ".cs", ".swift", ".kt", ".rs", ".scala", ".m", ".mm",
    ".vue", ".svelte",
}
SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", "venv", ".venv", "__pycache__",
    ".next", ".nuxt", "out", "target", ".idea", ".vscode", "coverage", ".mypy_cache",
}
MAX_FILES_PER_SCAN = 30
MAX_FILE_BYTES = 8000           # truncate each file to this many chars for the prompt
MAX_ZIP_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_ZIP_FILES = 2000

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

PROVIDERS = {"sonarqube", "sonarcloud", "snyk", "github_advanced_security", "semgrep", "custom"}


# ----------------------------- Models -----------------------------
ScanStatus = Literal["queued", "scanning", "done", "failed"]
ScanSource = Literal["github", "upload", "integration"]
IssueSeverity = Literal["blocker", "critical", "major", "minor", "info"]
IssueType = Literal["bug", "vulnerability", "code_smell", "security_hotspot"]


class GithubScanReq(BaseModel):
    repo_url: str
    branch: Optional[str] = None
    github_token: Optional[str] = None  # PAT for private repos


class IntegrationIn(BaseModel):
    name: str
    provider: Literal["sonarqube", "sonarcloud", "snyk", "github_advanced_security", "semgrep", "custom"]
    base_url: str
    token: str
    project_key: Optional[str] = None     # SonarQube projectKey, GH "owner/repo", Semgrep deployment slug, Snyk project id
    org: Optional[str] = None             # Snyk org id, SonarCloud organization
    extra: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class IntegrationPatch(BaseModel):
    enabled: Optional[bool] = None
    name: Optional[str] = None


class FixReq(BaseModel):
    github_repo: Optional[str] = None     # "owner/repo" — for auto-fetching the file
    github_token: Optional[str] = None
    branch: Optional[str] = None
    user_snippet: Optional[str] = None    # if the user wants to paste source manually


# ----------------------------- Utilities -----------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id() -> str:
    return uuid.uuid4().hex


def _truncate(text: str, limit: int = MAX_FILE_BYTES) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n# ...truncated {len(text) - limit} chars..."


def _public_integration(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Strip the token before returning to the client."""
    safe = {k: v for k, v in doc.items() if k != "token" and k != "_id"}
    safe["token_set"] = bool(doc.get("token"))
    return safe


def _public_scan(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in doc.items() if k != "_id"}


def _parse_github_url(url: str) -> Optional[Dict[str, str]]:
    """Accepts https://github.com/owner/repo[.git][/...]; returns {owner, repo}."""
    if not url:
        return None
    m = re.match(r"^https?://github\.com/([^/]+)/([^/.]+)(?:\.git)?(?:/.*)?$", url.strip().rstrip("/"))
    if not m:
        return None
    return {"owner": m.group(1), "repo": m.group(2)}


def _iter_source_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in CODE_EXTS:
            continue
        try:
            if p.stat().st_size > 200_000:  # skip huge files
                continue
        except OSError:
            continue
        files.append(p)
        if len(files) >= MAX_FILES_PER_SCAN:
            break
    return files


# ----------------------------- Claude prompts -----------------------------
ANALYZER_SYSTEM = """You are a senior static-analysis engine. Given source files, find real code-quality problems and return STRICT JSON only.

For each problem produce: rule (short snake_case identifier, e.g. "py:unused-variable"), severity (one of blocker|critical|major|minor|info), type (one of bug|vulnerability|code_smell|security_hotspot), file (relative path), line (1-indexed integer), message (one-line human description), recommendation (short fix suggestion), snippet (the offending line(s), max 4 lines).

Rules:
- Focus on bugs, security issues, code smells, anti-patterns. Skip pure style/formatting.
- Be precise about line numbers.
- If nothing is wrong, return an empty array.
- Output ONLY a JSON array. No prose, no markdown fences.
"""

FIXER_SYSTEM = """You are a senior software engineer. Given a single code-quality issue and the full source of the affected file, produce a concrete, minimal patch.

Return STRICT JSON only with these fields:
  explanation : short paragraph explaining the issue and the fix
  patched_file: the FULL patched file content (string)
  diff        : a unified diff (a/<file> -> b/<file>) showing the change
  test_hint   : one-line suggestion on how to verify the fix

Output ONLY the JSON object. No prose, no markdown fences.
"""


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n", "", s)
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


async def _claude(system: str, prompt: str, session_id: str) -> str:
    if not EMERGENT_LLM_KEY:
        raise RuntimeError("EMERGENT_LLM_KEY is not set")
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system,
    ).with_model("anthropic", CLAUDE_MODEL)
    msg = UserMessage(text=prompt)
    resp = await chat.send_message(msg)
    return resp if isinstance(resp, str) else str(resp)


async def _analyze_files_with_claude(files: List[Dict[str, str]], session_id: str) -> List[Dict[str, Any]]:
    """files = [{path, content}]. Returns list of issues with absolute paths preserved."""
    if not files:
        return []
    payload = "Analyze the following source files and return a JSON array of issues.\n\n"
    for f in files:
        payload += f"=== FILE: {f['path']} ===\n{_truncate(f['content'])}\n\n"
    raw = await _claude(ANALYZER_SYSTEM, payload, session_id)
    raw = _strip_code_fence(raw)
    try:
        data = json.loads(raw)
    except Exception as e:
        logger.warning("Analyzer returned non-JSON: %s | raw=%s", e, raw[:300])
        # Try to extract the first JSON array substring
        m = re.search(r"\[.*\]", raw, re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    for it in data:
        if not isinstance(it, dict):
            continue
        cleaned.append({
            "rule": str(it.get("rule") or "unknown"),
            "severity": _norm_severity(it.get("severity")),
            "type": _norm_type(it.get("type")),
            "file": str(it.get("file") or ""),
            "line": int(it.get("line") or 1) if str(it.get("line") or "").strip().lstrip("-").isdigit() else 1,
            "message": str(it.get("message") or "")[:500],
            "recommendation": str(it.get("recommendation") or "")[:600],
            "snippet": str(it.get("snippet") or "")[:1000],
        })
    return cleaned


def _norm_severity(v: Any) -> str:
    v = str(v or "").lower().strip()
    if v in {"blocker", "critical", "major", "minor", "info"}:
        return v
    # Map common synonyms (Sonar uses these; Snyk uses high/medium/low)
    mapping = {
        "high": "major",
        "medium": "minor",
        "low": "info",
        "warning": "minor",
        "error": "major",
        "note": "info",
    }
    return mapping.get(v, "minor")


def _norm_type(v: Any) -> str:
    v = str(v or "").lower().strip().replace("-", "_").replace(" ", "_")
    if v in {"bug", "vulnerability", "code_smell", "security_hotspot"}:
        return v
    if "security" in v or v == "hotspot":
        return "security_hotspot"
    if v in {"vuln", "vulnerabilities"}:
        return "vulnerability"
    if v in {"smell", "smells"}:
        return "code_smell"
    return "bug"


# ----------------------------- External fetchers -----------------------------
async def _fetch_sonarqube_issues(base_url: str, token: str, project_key: str, organization: Optional[str] = None) -> List[Dict[str, Any]]:
    """Works for SonarQube and SonarCloud."""
    if not project_key:
        raise HTTPException(400, "project_key is required for SonarQube/SonarCloud")
    base = base_url.rstrip("/")
    auth = (token, "")  # SonarQube uses HTTP basic with token as username
    params = {"componentKeys": project_key, "ps": 100, "additionalFields": "_all", "resolved": "false"}
    if organization:
        params["organization"] = organization
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{base}/api/issues/search", params=params, auth=auth)
        if r.status_code == 401:
            raise HTTPException(401, "SonarQube auth failed — token rejected")
        r.raise_for_status()
        data = r.json()
    out: List[Dict[str, Any]] = []
    for it in data.get("issues", []):
        comp = it.get("component", "")
        file_path = comp.split(":", 1)[1] if ":" in comp else comp
        out.append({
            "rule": it.get("rule") or "sonar",
            "severity": _norm_severity(it.get("severity")),
            "type": _norm_type(it.get("type")),
            "file": file_path,
            "line": int(it.get("line") or 1),
            "message": it.get("message") or "",
            "recommendation": "",
            "snippet": "",
            "external_id": it.get("key"),
        })
    return out


async def _fetch_snyk_issues(token: str, org: str, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if not org:
        raise HTTPException(400, "org is required for Snyk")
    headers = {"Authorization": f"token {token}", "Content-Type": "application/vnd.api+json"}
    url = f"https://api.snyk.io/rest/orgs/{org}/issues"
    params = {"version": "2024-04-22", "limit": 100}
    if project_id:
        params["scan_item.id"] = project_id
        params["scan_item.type"] = "project"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, params=params, headers=headers)
        if r.status_code == 401:
            raise HTTPException(401, "Snyk auth failed — token rejected")
        r.raise_for_status()
        data = r.json()
    out: List[Dict[str, Any]] = []
    for it in data.get("data", []):
        attrs = it.get("attributes", {}) or {}
        out.append({
            "rule": attrs.get("key") or attrs.get("type") or "snyk",
            "severity": _norm_severity(attrs.get("effective_severity_level") or attrs.get("severity")),
            "type": "vulnerability" if (attrs.get("type") or "").lower().startswith("vuln") else "code_smell",
            "file": (attrs.get("coordinates") or [{}])[0].get("representations", [{}])[0].get("sourceLocation", {}).get("file", "") if attrs.get("coordinates") else "",
            "line": int(((attrs.get("coordinates") or [{}])[0].get("representations", [{}])[0].get("sourceLocation", {}).get("region", {}).get("start", {}) or {}).get("line", 1)) if attrs.get("coordinates") else 1,
            "message": attrs.get("title") or "",
            "recommendation": "",
            "snippet": "",
            "external_id": it.get("id"),
        })
    return out


async def _fetch_github_code_scanning(token: str, repo: str) -> List[Dict[str, Any]]:
    if "/" not in (repo or ""):
        raise HTTPException(400, "project_key for GitHub must be 'owner/repo'")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{repo}/code-scanning/alerts"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=headers, params={"per_page": 100, "state": "open"})
        if r.status_code == 401:
            raise HTTPException(401, "GitHub auth failed — PAT rejected (needs `security_events` scope)")
        if r.status_code == 404:
            raise HTTPException(404, "Repo not found or code scanning not enabled")
        r.raise_for_status()
        data = r.json()
    out: List[Dict[str, Any]] = []
    for it in data:
        rule = (it.get("rule") or {}).get("id") or "codeql"
        sev = (it.get("rule") or {}).get("severity") or (it.get("rule") or {}).get("security_severity_level")
        most_recent = it.get("most_recent_instance") or {}
        loc = (most_recent.get("location") or {})
        out.append({
            "rule": rule,
            "severity": _norm_severity(sev),
            "type": "security_hotspot" if "security" in str(rule).lower() else "code_smell",
            "file": loc.get("path") or "",
            "line": int(loc.get("start_line") or 1),
            "message": most_recent.get("message", {}).get("text") or (it.get("rule") or {}).get("description") or "",
            "recommendation": (it.get("rule") or {}).get("help") or "",
            "snippet": "",
            "external_id": str(it.get("number")),
        })
    return out


async def _fetch_semgrep_findings(token: str, deployment_slug: str) -> List[Dict[str, Any]]:
    if not deployment_slug:
        raise HTTPException(400, "project_key (deployment slug) is required for Semgrep")
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://semgrep.dev/api/v1/deployments/{deployment_slug}/findings"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=headers, params={"page_size": 100})
        if r.status_code == 401:
            raise HTTPException(401, "Semgrep auth failed — token rejected")
        r.raise_for_status()
        data = r.json()
    out: List[Dict[str, Any]] = []
    for it in data.get("findings", []):
        out.append({
            "rule": it.get("rule_name") or "semgrep",
            "severity": _norm_severity(it.get("severity")),
            "type": "security_hotspot" if "security" in (it.get("rule_name") or "").lower() else "code_smell",
            "file": (it.get("location") or {}).get("file_path") or "",
            "line": int((it.get("location") or {}).get("line") or 1),
            "message": it.get("rule_message") or "",
            "recommendation": "",
            "snippet": (it.get("line_of_code") or "")[:1000],
            "external_id": str(it.get("id")),
        })
    return out


async def _fetch_custom(integration: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Custom: GET base_url with optional auth header. Returns raw list, mapped by `field_map` in extra."""
    base = integration["base_url"]
    extra = integration.get("extra") or {}
    auth_header = extra.get("auth_header", "Authorization")
    auth_prefix = extra.get("auth_prefix", "Bearer ")
    headers = {auth_header: f"{auth_prefix}{integration['token']}"} if integration.get("token") else {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(base, headers=headers)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, f"Custom scanner returned {r.status_code}: {r.text[:200]}")
        try:
            data = r.json()
        except Exception:
            raise HTTPException(500, "Custom scanner response is not JSON")
    items = data if isinstance(data, list) else (data.get("issues") or data.get("findings") or data.get("data") or [])
    fm = extra.get("field_map") or {}
    out: List[Dict[str, Any]] = []
    for it in items[:200] if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        out.append({
            "rule": str(it.get(fm.get("rule", "rule")) or "custom"),
            "severity": _norm_severity(it.get(fm.get("severity", "severity"))),
            "type": _norm_type(it.get(fm.get("type", "type"))),
            "file": str(it.get(fm.get("file", "file")) or ""),
            "line": int(it.get(fm.get("line", "line")) or 1) if str(it.get(fm.get("line", "line")) or "").strip().lstrip("-").isdigit() else 1,
            "message": str(it.get(fm.get("message", "message")) or "")[:500],
            "recommendation": str(it.get(fm.get("recommendation", "recommendation")) or "")[:600],
            "snippet": str(it.get(fm.get("snippet", "snippet")) or "")[:1000],
            "external_id": str(it.get(fm.get("id", "id")) or "") or None,
        })
    return out


# ----------------------------- Router factory -----------------------------
def build_router(db, get_current_user) -> APIRouter:
    """Returns a FastAPI APIRouter wired with the given db & auth dependency."""
    router = APIRouter(prefix="/code-quality", tags=["code-quality-v2"])

    # ---------- helpers (closure over db) ----------
    async def _insert_scan(user_email: str, source: str, source_label: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        scan = {
            "id": _safe_id(),
            "user_email": user_email,
            "source": source,
            "source_label": source_label,
            "meta": meta,
            "status": "queued",
            "totals": {"total": 0, "bug": 0, "vulnerability": 0, "code_smell": 0, "security_hotspot": 0},
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "error": None,
            "file_count": 0,
        }
        await db.cq_scans.insert_one(scan)
        return scan

    async def _mark_scan(scan_id: str, **fields):
        if not fields:
            return
        await db.cq_scans.update_one({"id": scan_id}, {"$set": fields})

    async def _save_issues(scan_id: str, user_email: str, issues: List[Dict[str, Any]]):
        if not issues:
            return
        docs = []
        totals = {"total": 0, "bug": 0, "vulnerability": 0, "code_smell": 0, "security_hotspot": 0}
        for it in issues:
            t = it.get("type") or "bug"
            totals["total"] += 1
            totals[t] = totals.get(t, 0) + 1
            docs.append({
                "id": _safe_id(),
                "scan_id": scan_id,
                "user_email": user_email,
                "rule": it.get("rule", ""),
                "severity": it.get("severity", "minor"),
                "type": t,
                "file": it.get("file", ""),
                "line": int(it.get("line", 1) or 1),
                "message": it.get("message", ""),
                "recommendation": it.get("recommendation", ""),
                "snippet": it.get("snippet", ""),
                "external_id": it.get("external_id"),
                "created_at": _now(),
                "fix": None,
            })
        await db.cq_issues.insert_many(docs)
        await db.cq_scans.update_one({"id": scan_id}, {"$set": {"totals": totals}})

    # ---------- Scans: GitHub ----------
    async def _run_github_scan(scan_id: str, user_email: str, repo_url: str, branch: Optional[str], token: Optional[str]):
        tmp = Path(tempfile.mkdtemp(prefix="cq_gh_"))
        try:
            await _mark_scan(scan_id, status="scanning", started_at=_now())
            # Build clone URL with optional token
            clone_url = repo_url
            if token:
                # Inject token into URL: https://<token>@github.com/owner/repo
                clone_url = re.sub(r"^https?://", f"https://{token}@", repo_url)
            cmd = ["git", "clone", "--depth", "1"]
            if branch:
                cmd += ["--branch", branch]
            cmd += [clone_url, str(tmp / "repo")]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="ignore")
                # Sanitize token from error message
                if token:
                    err = err.replace(token, "***")
                raise RuntimeError(f"git clone failed: {err[:500]}")
            repo_dir = tmp / "repo"
            files = _iter_source_files(repo_dir)
            await _mark_scan(scan_id, file_count=len(files))
            payload = []
            for fp in files:
                try:
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                payload.append({"path": str(fp.relative_to(repo_dir)), "content": text})
            issues = await _analyze_files_with_claude(payload, session_id=f"cq-scan-{scan_id}")
            await _save_issues(scan_id, user_email, issues)
            await _mark_scan(scan_id, status="done", finished_at=_now())
        except Exception as e:
            logger.exception("github scan failed")
            await _mark_scan(scan_id, status="failed", finished_at=_now(), error=str(e)[:500])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @router.post("/scans/github")
    async def scan_github(
        body: GithubScanReq,
        background_tasks: BackgroundTasks,
        current_user: dict = Depends(get_current_user),
    ):
        parsed = _parse_github_url(body.repo_url)
        if not parsed:
            raise HTTPException(400, "Invalid GitHub URL. Expected https://github.com/owner/repo")
        scan = await _insert_scan(
            user_email=current_user["email"],
            source="github",
            source_label=f"{parsed['owner']}/{parsed['repo']}" + (f"@{body.branch}" if body.branch else ""),
            meta={"repo_url": body.repo_url, "branch": body.branch, "has_token": bool(body.github_token)},
        )
        background_tasks.add_task(
            _run_github_scan, scan["id"], current_user["email"], body.repo_url, body.branch, body.github_token
        )
        return _public_scan(scan)

    # ---------- Scans: Upload ----------
    async def _run_upload_scan(scan_id: str, user_email: str, zip_path: str, original_name: str):
        tmp = Path(tempfile.mkdtemp(prefix="cq_up_"))
        try:
            await _mark_scan(scan_id, status="scanning", started_at=_now())
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                if len(names) > MAX_ZIP_FILES:
                    raise RuntimeError(f"Zip has {len(names)} files (max {MAX_ZIP_FILES})")
                # Safe extract — block path traversal
                for n in names:
                    if n.startswith("/") or ".." in Path(n).parts:
                        continue
                    zf.extract(n, tmp)
            files = _iter_source_files(tmp)
            await _mark_scan(scan_id, file_count=len(files))
            payload = []
            for fp in files:
                try:
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                payload.append({"path": str(fp.relative_to(tmp)), "content": text})
            issues = await _analyze_files_with_claude(payload, session_id=f"cq-scan-{scan_id}")
            await _save_issues(scan_id, user_email, issues)
            await _mark_scan(scan_id, status="done", finished_at=_now())
        except Exception as e:
            logger.exception("upload scan failed")
            await _mark_scan(scan_id, status="failed", finished_at=_now(), error=str(e)[:500])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            try:
                os.unlink(zip_path)
            except OSError:
                pass

    @router.post("/scans/upload")
    async def scan_upload(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        current_user: dict = Depends(get_current_user),
    ):
        if not (file.filename or "").lower().endswith(".zip"):
            raise HTTPException(400, "Only .zip uploads are supported")
        # Save in chunks, enforce size cap
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="cq_up_")
        size = 0
        with os.fdopen(tmp_fd, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ZIP_SIZE:
                    out.close()
                    os.unlink(tmp_path)
                    raise HTTPException(413, f"Zip exceeds {MAX_ZIP_SIZE // (1024*1024)} MB cap")
                out.write(chunk)
        scan = await _insert_scan(
            user_email=current_user["email"],
            source="upload",
            source_label=file.filename or "upload.zip",
            meta={"original_name": file.filename, "size": size},
        )
        background_tasks.add_task(
            _run_upload_scan, scan["id"], current_user["email"], tmp_path, file.filename or "upload.zip"
        )
        return _public_scan(scan)

    # ---------- Scans: List / detail / delete ----------
    @router.get("/scans")
    async def list_scans(current_user: dict = Depends(get_current_user)):
        docs = await db.cq_scans.find({"user_email": current_user["email"]}).sort("created_at", -1).to_list(200)
        return [_public_scan(d) for d in docs]

    @router.get("/scans/{scan_id}")
    async def get_scan(scan_id: str, current_user: dict = Depends(get_current_user)):
        doc = await db.cq_scans.find_one({"id": scan_id, "user_email": current_user["email"]})
        if not doc:
            raise HTTPException(404, "Scan not found")
        return _public_scan(doc)

    @router.delete("/scans/{scan_id}")
    async def delete_scan(scan_id: str, current_user: dict = Depends(get_current_user)):
        r = await db.cq_scans.delete_one({"id": scan_id, "user_email": current_user["email"]})
        if r.deleted_count == 0:
            raise HTTPException(404, "Scan not found")
        await db.cq_issues.delete_many({"scan_id": scan_id})
        return {"ok": True}

    @router.get("/scans/{scan_id}/issues")
    async def get_scan_issues(
        scan_id: str,
        severity: Optional[str] = Query(None),
        type: Optional[str] = Query(None),
        current_user: dict = Depends(get_current_user),
    ):
        scan = await db.cq_scans.find_one({"id": scan_id, "user_email": current_user["email"]})
        if not scan:
            raise HTTPException(404, "Scan not found")
        q: Dict[str, Any] = {"scan_id": scan_id}
        if severity:
            q["severity"] = severity
        if type:
            q["type"] = type
        docs = await db.cq_issues.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
        return docs

    # ---------- Integrations ----------
    @router.get("/integrations")
    async def list_integrations(current_user: dict = Depends(get_current_user)):
        docs = await db.cq_integrations.find({"user_email": current_user["email"]}).sort("created_at", -1).to_list(100)
        return [_public_integration(d) for d in docs]

    @router.post("/integrations")
    async def create_integration(
        body: IntegrationIn,
        current_user: dict = Depends(get_current_user),
    ):
        if body.provider not in PROVIDERS:
            raise HTTPException(400, f"Unknown provider. Use one of: {sorted(PROVIDERS)}")
        doc = {
            "id": _safe_id(),
            "user_email": current_user["email"],
            "name": body.name,
            "provider": body.provider,
            "base_url": body.base_url.rstrip("/"),
            "token": body.token,
            "project_key": body.project_key,
            "org": body.org,
            "extra": body.extra or {},
            "enabled": body.enabled,
            "created_at": _now(),
            "last_sync_at": None,
            "last_status": None,
        }
        await db.cq_integrations.insert_one(doc)
        return _public_integration(doc)

    @router.patch("/integrations/{integration_id}")
    async def update_integration(
        integration_id: str,
        body: IntegrationPatch,
        current_user: dict = Depends(get_current_user),
    ):
        updates: Dict[str, Any] = {}
        if body.enabled is not None:
            updates["enabled"] = body.enabled
        if body.name is not None:
            updates["name"] = body.name
        if not updates:
            raise HTTPException(400, "No fields to update")
        r = await db.cq_integrations.update_one(
            {"id": integration_id, "user_email": current_user["email"]},
            {"$set": updates},
        )
        if r.matched_count == 0:
            raise HTTPException(404, "Integration not found")
        doc = await db.cq_integrations.find_one({"id": integration_id})
        return _public_integration(doc)

    @router.delete("/integrations/{integration_id}")
    async def delete_integration(integration_id: str, current_user: dict = Depends(get_current_user)):
        r = await db.cq_integrations.delete_one({"id": integration_id, "user_email": current_user["email"]})
        if r.deleted_count == 0:
            raise HTTPException(404, "Integration not found")
        return {"ok": True}

    @router.post("/integrations/{integration_id}/sync")
    async def sync_integration(integration_id: str, current_user: dict = Depends(get_current_user)):
        integ = await db.cq_integrations.find_one({"id": integration_id, "user_email": current_user["email"]})
        if not integ:
            raise HTTPException(404, "Integration not found")
        if not integ.get("enabled", True):
            raise HTTPException(400, "Integration is disabled. Enable it to sync.")
        scan = await _insert_scan(
            user_email=current_user["email"],
            source="integration",
            source_label=f"{integ['provider']}: {integ['name']}",
            meta={"integration_id": integration_id, "provider": integ["provider"]},
        )
        await _mark_scan(scan["id"], status="scanning", started_at=_now())
        try:
            provider = integ["provider"]
            if provider in ("sonarqube", "sonarcloud"):
                issues = await _fetch_sonarqube_issues(
                    integ["base_url"], integ["token"], integ.get("project_key") or "",
                    organization=integ.get("org") if provider == "sonarcloud" else None,
                )
            elif provider == "snyk":
                issues = await _fetch_snyk_issues(integ["token"], integ.get("org") or "", integ.get("project_key"))
            elif provider == "github_advanced_security":
                issues = await _fetch_github_code_scanning(integ["token"], integ.get("project_key") or "")
            elif provider == "semgrep":
                issues = await _fetch_semgrep_findings(integ["token"], integ.get("project_key") or "")
            elif provider == "custom":
                issues = await _fetch_custom(integ)
            else:
                raise HTTPException(400, f"Unsupported provider {provider}")
            await _save_issues(scan["id"], current_user["email"], issues)
            await _mark_scan(scan["id"], status="done", finished_at=_now())
            await db.cq_integrations.update_one(
                {"id": integration_id}, {"$set": {"last_sync_at": _now(), "last_status": "ok"}}
            )
        except HTTPException as he:
            await _mark_scan(scan["id"], status="failed", finished_at=_now(), error=he.detail)
            await db.cq_integrations.update_one(
                {"id": integration_id}, {"$set": {"last_sync_at": _now(), "last_status": f"error: {he.detail}"}}
            )
            raise
        except Exception as e:
            logger.exception("integration sync failed")
            await _mark_scan(scan["id"], status="failed", finished_at=_now(), error=str(e)[:500])
            await db.cq_integrations.update_one(
                {"id": integration_id}, {"$set": {"last_sync_at": _now(), "last_status": f"error: {str(e)[:200]}"}}
            )
            raise HTTPException(500, f"Sync failed: {str(e)[:200]}")
        return _public_scan(await db.cq_scans.find_one({"id": scan["id"]}))

    # ---------- Issue fix (Claude) ----------
    async def _fetch_github_file(repo: str, path: str, token: Optional[str], branch: Optional[str]) -> Optional[str]:
        if "/" not in repo:
            return None
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        params = {}
        if branch:
            params["ref"] = branch
        url = f"https://api.github.com/repos/{repo}/contents/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, headers=headers, params=params)
            if r.status_code != 200:
                return None
            data = r.json()
            content = data.get("content")
            if not content:
                return None
            try:
                return base64.b64decode(content).decode("utf-8", errors="ignore")
            except Exception:
                return None

    @router.post("/issues/{issue_id}/fix")
    async def generate_fix(
        issue_id: str,
        body: FixReq,
        current_user: dict = Depends(get_current_user),
    ):
        issue = await db.cq_issues.find_one({"id": issue_id, "user_email": current_user["email"]}, {"_id": 0})
        if not issue:
            raise HTTPException(404, "Issue not found")
        # Resolve file content
        file_content: Optional[str] = body.user_snippet
        if not file_content and body.github_repo and issue.get("file"):
            file_content = await _fetch_github_file(body.github_repo, issue["file"], body.github_token, body.branch)
        if not file_content:
            # Fall back to issue snippet (Claude still gives useful guidance)
            file_content = issue.get("snippet") or "# (full file not provided; only issue context is available)"
        prompt = (
            f"ISSUE:\n"
            f"  rule       : {issue.get('rule')}\n"
            f"  severity   : {issue.get('severity')}\n"
            f"  type       : {issue.get('type')}\n"
            f"  file       : {issue.get('file')}\n"
            f"  line       : {issue.get('line')}\n"
            f"  message    : {issue.get('message')}\n"
            f"  recommendation: {issue.get('recommendation')}\n\n"
            f"FULL FILE ({issue.get('file')}):\n"
            f"```\n{_truncate(file_content, 16000)}\n```\n\n"
            f"Produce the JSON fix object now."
        )
        raw = await _claude(FIXER_SYSTEM, prompt, session_id=f"cq-fix-{issue_id}")
        raw = _strip_code_fence(raw)
        try:
            fix = json.loads(raw)
        except Exception:
            m = re.search(r"\{.*\}", raw, re.S)
            if not m:
                raise HTTPException(500, "AI fixer returned non-JSON")
            fix = json.loads(m.group(0))
        fix_obj = {
            "explanation": str(fix.get("explanation") or "")[:4000],
            "patched_file": str(fix.get("patched_file") or "")[:200_000],
            "diff": str(fix.get("diff") or "")[:200_000],
            "test_hint": str(fix.get("test_hint") or "")[:500],
            "generated_at": _now(),
        }
        await db.cq_issues.update_one({"id": issue_id}, {"$set": {"fix": fix_obj}})
        return fix_obj

    @router.get("/issues/{issue_id}")
    async def get_issue(issue_id: str, current_user: dict = Depends(get_current_user)):
        doc = await db.cq_issues.find_one({"id": issue_id, "user_email": current_user["email"]}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Issue not found")
        return doc

    # ---------- Demo data seeder ----------
    @router.post("/demo/seed")
    async def seed_demo_data(
        reset: bool = Query(False, description="If true, delete all existing Code Quality v2 data for the user before seeding."),
        current_user: dict = Depends(get_current_user),
    ):
        """Seed a rich, realistic demo dataset for the current user — for client demos."""
        return await _seed_demo_for(db, current_user["email"], reset=reset)

    return router


# ----------------------------- Demo seeder -----------------------------
def _build_demo_dataset(user_email: str) -> Dict[str, List[Dict[str, Any]]]:
    """Returns ready-to-insert lists of integrations, scans, and issues for one user.

    Includes one disabled integration so the user can demonstrate the toggle.
    Includes one scan with a pre-baked AI fix so the user can show the fix flow
    immediately without burning an LLM call.
    """
    now = datetime.now(timezone.utc)
    def iso(mins_ago: int) -> str:
        return (now - timedelta(minutes=mins_ago)).isoformat()

    integrations = [
        {
            "id": _safe_id(),
            "user_email": user_email,
            "name": "SonarQube · Production",
            "provider": "sonarqube",
            "base_url": "https://sonar.acme-corp.com",
            "token": "sq_demo_" + uuid.uuid4().hex[:16],
            "project_key": "acme-checkout-service",
            "org": None,
            "extra": {},
            "enabled": True,
            "created_at": iso(60 * 24 * 5),
            "last_sync_at": iso(15),
            "last_status": "ok",
        },
        {
            "id": _safe_id(),
            "user_email": user_email,
            "name": "Snyk · Security",
            "provider": "snyk",
            "base_url": "https://api.snyk.io",
            "token": "snyk_demo_" + uuid.uuid4().hex[:16],
            "project_key": "5b8c8f3e-1234-4abc-9def-000000000001",
            "org": "acme-security",
            "extra": {},
            "enabled": True,
            "created_at": iso(60 * 24 * 3),
            "last_sync_at": iso(45),
            "last_status": "ok",
        },
        {
            "id": _safe_id(),
            "user_email": user_email,
            "name": "Semgrep Cloud · Staging",
            "provider": "semgrep",
            "base_url": "https://semgrep.dev",
            "token": "semgrep_demo_" + uuid.uuid4().hex[:16],
            "project_key": "acme-staging",
            "org": None,
            "extra": {},
            "enabled": False,  # disabled — for demoing the toggle
            "created_at": iso(60 * 24 * 1),
            "last_sync_at": iso(60 * 12),
            "last_status": "ok",
        },
    ]

    scans: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []

    # --- Scan A: GitHub repo, done, RICH issue list, ONE with a pre-baked fix ---
    scan_a_id = _safe_id()
    scan_a_issues = [
        {
            "rule": "py:hardcoded-secret",
            "severity": "blocker",
            "type": "vulnerability",
            "file": "src/auth/login.py",
            "line": 14,
            "message": "Hardcoded password literal used as authentication credential.",
            "recommendation": "Move the secret to an environment variable or a secrets manager.",
            "snippet": "PASSWORD = \"sup3r-s3cret-2025\"\nif user_pw == PASSWORD:\n    return True",
        },
        {
            "rule": "py:sql-injection",
            "severity": "critical",
            "type": "vulnerability",
            "file": "src/api/users.py",
            "line": 87,
            "message": "User input concatenated directly into SQL — risk of injection.",
            "recommendation": "Use parameterised queries with placeholders.",
            "snippet": "cursor.execute(\n    \"SELECT * FROM users WHERE email = '\" + email + \"'\"\n)",
        },
        {
            "rule": "py:dangerous-eval",
            "severity": "critical",
            "type": "vulnerability",
            "file": "src/utils/parser.py",
            "line": 22,
            "message": "Use of eval() on untrusted input.",
            "recommendation": "Replace eval() with ast.literal_eval() or a strict parser.",
            "snippet": "value = eval(request.json[\"expr\"])",
        },
        {
            "rule": "js:no-unused-vars",
            "severity": "minor",
            "type": "code_smell",
            "file": "frontend/src/components/Cart.jsx",
            "line": 41,
            "message": "Unused variable 'discount' declared but never used.",
            "recommendation": "Remove the variable or prefix with _.",
            "snippet": "const discount = computeDiscount(items);  // never read",
        },
        {
            "rule": "py:broad-except",
            "severity": "major",
            "type": "code_smell",
            "file": "src/api/orders.py",
            "line": 156,
            "message": "Catching bare Exception swallows useful tracebacks.",
            "recommendation": "Catch the specific exception you expect.",
            "snippet": "try:\n    process(order)\nexcept Exception:\n    return None",
        },
        {
            "rule": "py:weak-crypto",
            "severity": "major",
            "type": "security_hotspot",
            "file": "src/utils/hashing.py",
            "line": 9,
            "message": "MD5 is cryptographically broken — do not use for password hashing.",
            "recommendation": "Use bcrypt/argon2 with a per-user salt.",
            "snippet": "import hashlib\nhash = hashlib.md5(password.encode()).hexdigest()",
        },
        {
            "rule": "py:null-deref",
            "severity": "major",
            "type": "bug",
            "file": "src/services/payment.py",
            "line": 203,
            "message": "Possible None dereference: `customer.address.city` when address is None.",
            "recommendation": "Guard with `if customer.address is not None` before access.",
            "snippet": "city = customer.address.city",
        },
        {
            "rule": "js:react-hook-deps",
            "severity": "info",
            "type": "code_smell",
            "file": "frontend/src/pages/Cart.jsx",
            "line": 58,
            "message": "React Hook useEffect has a missing dependency: 'fetchCart'.",
            "recommendation": "Add fetchCart to the dependency array, or memoise it with useCallback.",
            "snippet": "useEffect(() => {\n  fetchCart();\n}, []);",
        },
    ]
    scans.append({
        "id": scan_a_id,
        "user_email": user_email,
        "source": "github",
        "source_label": "acme-corp/checkout-service@main",
        "meta": {"repo_url": "https://github.com/acme-corp/checkout-service", "branch": "main", "has_token": True},
        "status": "done",
        "totals": _compute_totals(scan_a_issues),
        "created_at": iso(60 * 2),
        "started_at": iso(60 * 2 - 1),
        "finished_at": iso(60 * 2 - 4),
        "error": None,
        "file_count": 28,
    })
    pre_baked_fix = {
        "explanation": (
            "The literal password in src/auth/login.py is committed to source control "
            "and shared by every deployment. Anyone with repo read access (current "
            "employees, contractors, or an attacker who steals a clone) gets the "
            "production credential.\n\nFix: read the secret from an environment "
            "variable, fail fast if it is missing in non-dev, and use a constant-"
            "time comparison (hmac.compare_digest) so timing side channels do not "
            "leak the value."
        ),
        "patched_file": (
            "import os\n"
            "import hmac\n"
            "from typing import Optional\n\n"
            "PASSWORD: Optional[str] = os.environ.get(\"APP_LOGIN_PASSWORD\")\n"
            "if not PASSWORD and os.environ.get(\"APP_ENV\", \"dev\") != \"dev\":\n"
            "    raise RuntimeError(\"APP_LOGIN_PASSWORD must be set outside dev\")\n\n"
            "def is_valid_login(user_pw: str) -> bool:\n"
            "    if PASSWORD is None:\n"
            "        return False\n"
            "    return hmac.compare_digest(user_pw, PASSWORD)\n"
        ),
        "diff": (
            "--- a/src/auth/login.py\n"
            "+++ b/src/auth/login.py\n"
            "@@ -12,8 +12,14 @@\n"
            "-PASSWORD = \"sup3r-s3cret-2025\"\n"
            "+import os, hmac\n"
            "+PASSWORD = os.environ.get(\"APP_LOGIN_PASSWORD\")\n"
            "+if not PASSWORD and os.environ.get(\"APP_ENV\", \"dev\") != \"dev\":\n"
            "+    raise RuntimeError(\"APP_LOGIN_PASSWORD must be set outside dev\")\n"
            "-if user_pw == PASSWORD:\n"
            "-    return True\n"
            "+def is_valid_login(user_pw: str) -> bool:\n"
            "+    if PASSWORD is None:\n"
            "+        return False\n"
            "+    return hmac.compare_digest(user_pw, PASSWORD)\n"
        ),
        "test_hint": "Set APP_LOGIN_PASSWORD in your test runner and assert is_valid_login() returns False for any other string.",
        "generated_at": iso(60 * 2 - 3),
    }
    for idx, it in enumerate(scan_a_issues):
        issues.append({
            "id": _safe_id(),
            "scan_id": scan_a_id,
            "user_email": user_email,
            "rule": it["rule"],
            "severity": it["severity"],
            "type": it["type"],
            "file": it["file"],
            "line": it["line"],
            "message": it["message"],
            "recommendation": it["recommendation"],
            "snippet": it["snippet"],
            "external_id": None,
            "created_at": iso(60 * 2 - 4),
            "fix": pre_baked_fix if idx == 0 else None,
        })

    # --- Scan B: Uploaded .zip, done ---
    scan_b_id = _safe_id()
    scan_b_issues = [
        {
            "rule": "js:no-console",
            "severity": "info",
            "type": "code_smell",
            "file": "src/utils/logger.js",
            "line": 4,
            "message": "console.log left in production build.",
            "recommendation": "Use a structured logger or strip in build.",
            "snippet": "console.log(\"DEBUG\", payload);",
        },
        {
            "rule": "ts:any-type",
            "severity": "minor",
            "type": "code_smell",
            "file": "src/api/client.ts",
            "line": 19,
            "message": "Function returns `any`, defeating type checking.",
            "recommendation": "Add an explicit return type.",
            "snippet": "export function fetchJson(url: string): any { ... }",
        },
        {
            "rule": "js:weak-jwt-verify",
            "severity": "major",
            "type": "vulnerability",
            "file": "src/middleware/auth.js",
            "line": 31,
            "message": "JWT verified without checking algorithm whitelist.",
            "recommendation": "Pass `{ algorithms: ['HS256'] }` to jwt.verify.",
            "snippet": "jwt.verify(token, secret); // missing algorithms whitelist",
        },
    ]
    scans.append({
        "id": scan_b_id,
        "user_email": user_email,
        "source": "upload",
        "source_label": "frontend-monorepo.zip",
        "meta": {"original_name": "frontend-monorepo.zip", "size": 4_812_345},
        "status": "done",
        "totals": _compute_totals(scan_b_issues),
        "created_at": iso(60 * 6),
        "started_at": iso(60 * 6 - 1),
        "finished_at": iso(60 * 6 - 3),
        "error": None,
        "file_count": 17,
    })
    for it in scan_b_issues:
        issues.append({
            "id": _safe_id(),
            "scan_id": scan_b_id,
            "user_email": user_email,
            "rule": it["rule"],
            "severity": it["severity"],
            "type": it["type"],
            "file": it["file"],
            "line": it["line"],
            "message": it["message"],
            "recommendation": it["recommendation"],
            "snippet": it["snippet"],
            "external_id": None,
            "created_at": iso(60 * 6 - 3),
            "fix": None,
        })

    # --- Scan C: SonarQube integration sync, done ---
    sonar_integration_id = integrations[0]["id"]
    scan_c_id = _safe_id()
    scan_c_issues = [
        {
            "rule": "java:S2095",
            "severity": "major",
            "type": "bug",
            "file": "src/main/java/com/acme/checkout/PaymentService.java",
            "line": 142,
            "message": "Resources should be closed (FileInputStream not closed in catch path).",
            "recommendation": "Use try-with-resources to guarantee close.",
            "snippet": "FileInputStream fis = new FileInputStream(file);\n// ... no close in catch",
        },
        {
            "rule": "java:S1192",
            "severity": "minor",
            "type": "code_smell",
            "file": "src/main/java/com/acme/checkout/OrderController.java",
            "line": 56,
            "message": "String literal \"order_id\" duplicated 8 times.",
            "recommendation": "Extract to a constant.",
            "snippet": "headers.put(\"order_id\", id);",
        },
        {
            "rule": "java:S2068",
            "severity": "blocker",
            "type": "vulnerability",
            "file": "src/main/java/com/acme/checkout/DbConfig.java",
            "line": 23,
            "message": "Hardcoded credentials in source.",
            "recommendation": "Read from environment / secrets manager.",
            "snippet": "private static final String DB_PWD = \"acme-prod-2024\";",
        },
        {
            "rule": "java:S5547",
            "severity": "major",
            "type": "security_hotspot",
            "file": "src/main/java/com/acme/checkout/Crypto.java",
            "line": 11,
            "message": "DES is a weak cipher.",
            "recommendation": "Use AES-256-GCM.",
            "snippet": "Cipher cipher = Cipher.getInstance(\"DES\");",
        },
    ]
    scans.append({
        "id": scan_c_id,
        "user_email": user_email,
        "source": "integration",
        "source_label": f"sonarqube: {integrations[0]['name']}",
        "meta": {"integration_id": sonar_integration_id, "provider": "sonarqube"},
        "status": "done",
        "totals": _compute_totals(scan_c_issues),
        "created_at": iso(15),
        "started_at": iso(15),
        "finished_at": iso(14),
        "error": None,
        "file_count": 0,
    })
    for it in scan_c_issues:
        issues.append({
            "id": _safe_id(),
            "scan_id": scan_c_id,
            "user_email": user_email,
            "rule": it["rule"],
            "severity": it["severity"],
            "type": it["type"],
            "file": it["file"],
            "line": it["line"],
            "message": it["message"],
            "recommendation": it["recommendation"],
            "snippet": it["snippet"],
            "external_id": f"AYM-{uuid.uuid4().hex[:8].upper()}",
            "created_at": iso(14),
            "fix": None,
        })

    # --- Scan D: Snyk integration sync, done ---
    snyk_integration_id = integrations[1]["id"]
    scan_d_id = _safe_id()
    scan_d_issues = [
        {
            "rule": "SNYK-JS-LODASH-567746",
            "severity": "critical",
            "type": "vulnerability",
            "file": "package.json",
            "line": 1,
            "message": "lodash 4.17.15 — Prototype Pollution (CVE-2020-8203).",
            "recommendation": "Upgrade lodash to >=4.17.20.",
            "snippet": "\"lodash\": \"4.17.15\"",
        },
        {
            "rule": "SNYK-PYTHON-DJANGO-1234567",
            "severity": "major",
            "type": "vulnerability",
            "file": "requirements.txt",
            "line": 3,
            "message": "Django 3.0.5 — SQL Injection via QuerySet.order_by (CVE-2020-9402).",
            "recommendation": "Upgrade Django to >=3.0.6.",
            "snippet": "Django==3.0.5",
        },
    ]
    scans.append({
        "id": scan_d_id,
        "user_email": user_email,
        "source": "integration",
        "source_label": f"snyk: {integrations[1]['name']}",
        "meta": {"integration_id": snyk_integration_id, "provider": "snyk"},
        "status": "done",
        "totals": _compute_totals(scan_d_issues),
        "created_at": iso(45),
        "started_at": iso(45),
        "finished_at": iso(44),
        "error": None,
        "file_count": 0,
    })
    for it in scan_d_issues:
        issues.append({
            "id": _safe_id(),
            "scan_id": scan_d_id,
            "user_email": user_email,
            "rule": it["rule"],
            "severity": it["severity"],
            "type": it["type"],
            "file": it["file"],
            "line": it["line"],
            "message": it["message"],
            "recommendation": it["recommendation"],
            "snippet": it["snippet"],
            "external_id": f"SNYK-{uuid.uuid4().hex[:8]}",
            "created_at": iso(44),
            "fix": None,
        })

    # --- Scan E: Failed GitHub scan (private repo, bad token) ---
    scans.append({
        "id": _safe_id(),
        "user_email": user_email,
        "source": "github",
        "source_label": "acme-corp/internal-billing",
        "meta": {"repo_url": "https://github.com/acme-corp/internal-billing", "branch": None, "has_token": True},
        "status": "failed",
        "totals": {"total": 0, "bug": 0, "vulnerability": 0, "code_smell": 0, "security_hotspot": 0},
        "created_at": iso(8),
        "started_at": iso(8),
        "finished_at": iso(8),
        "error": "git clone failed: remote: Repository not found.",
        "file_count": 0,
    })

    return {"integrations": integrations, "scans": scans, "issues": issues}


def _compute_totals(issue_dicts: List[Dict[str, Any]]) -> Dict[str, int]:
    t = {"total": 0, "bug": 0, "vulnerability": 0, "code_smell": 0, "security_hotspot": 0}
    for it in issue_dicts:
        t["total"] += 1
        k = it.get("type", "bug")
        t[k] = t.get(k, 0) + 1
    return t


async def _seed_demo_for(db, user_email: str, reset: bool = False) -> Dict[str, Any]:
    if reset:
        await db.cq_integrations.delete_many({"user_email": user_email})
        await db.cq_scans.delete_many({"user_email": user_email})
        await db.cq_issues.delete_many({"user_email": user_email})
    data = _build_demo_dataset(user_email)
    if data["integrations"]:
        await db.cq_integrations.insert_many(data["integrations"])
    if data["scans"]:
        await db.cq_scans.insert_many(data["scans"])
    if data["issues"]:
        await db.cq_issues.insert_many(data["issues"])
    return {
        "ok": True,
        "reset": reset,
        "integrations_added": len(data["integrations"]),
        "scans_added": len(data["scans"]),
        "issues_added": len(data["issues"]),
    }
