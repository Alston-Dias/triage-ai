# TriageAI + Mocked SonarQube Integration — PRD

## Original Problem Statement
Analyze the repository and implement the minimal required setup for SonarQube integration.
Evolved into:
1. Use mocked/static data for SonarQube (no live SonarQube server).
2. Integrate the mocked SonarQube Code Quality dashboard as a new tab/feature into the `triage-ai` application (cloned from https://github.com/simransirsat/triage-ai.git).
3. Restructure so the cloned repo lives at `/app/` (workspace root) so Emergent's "Save to GitHub" works.

## Active Workspace
`/app/` (was `/app/triage-ai-integration/`, flattened on 2026-05-14 — `.git` preserved, remote still `https://github.com/simransirsat/triage-ai.git`).

## Services (supervisor — `/etc/supervisor/conf.d/supervisord.conf` defaults)
- `backend` — FastAPI on port 8001 (directory `/app/backend`)
- `frontend` — React (craco) on port 3000 (directory `/app/frontend`)
- `mongodb` — local Mongo

## Auth (pre-seeded users — see `SEED_USERS` in `/app/backend/server.py`)
| Role | Email | Password |
|---|---|---|
| Admin | admin@triage.ai | admin123 |
| On-call | sre1@triage.ai | sre123 |
| On-call | sre2@triage.ai | sre123 |
| Viewer | viewer@triage.ai | viewer123 |

Login: `POST /api/auth/login` → returns JWT + user object. Token stored as `triage_token` in localStorage.

## SonarQube Mock API
**Read endpoints (no auth):**
- `GET /api/sonarqube/summary` — project metadata, bugs/vulnerabilities/codeSmells/coverage/duplications/LOC + ratings
- `GET /api/sonarqube/issues` — list of issues with extended fields (title, description, rule, suggestedFix, assignee, status, type, severity, component/line, effort, tags)
- `GET /api/sonarqube/quality-gate` — gate status + condition rows

**Issue workflow endpoints (Bearer token required):**
- `GET /api/sonarqube/issues/{key}` — full detail for one issue
- `POST /api/sonarqube/issues/{key}/claim` — assignee = current user, status = CLAIMED
- `POST /api/sonarqube/issues/{key}/assign` body `{email}` — assignee = email (OPEN auto-bumps to CLAIMED). 404 if user unknown.
- `PATCH /api/sonarqube/issues/{key}/status` body `{status}` — status ∈ {OPEN, CLAIMED, IN_PROGRESS, FIXED}. Setting OPEN clears assignee.

**AI Remediation Assistant (Bearer token required, mocked replies):**
- `GET /api/sonarqube/issues/{key}/chat` — chat history (empty list initially)
- `POST /api/sonarqube/issues/{key}/chat` body `{text, intent?}` — appends user msg + mocked assistant reply. Intent ∈ {explain, suggest_fix, refactor, severity, best_practices}; if omitted, keyword-routed by `_detect_intent`. Assistant message includes `intent` field. Persists in `db.sonarqube_chats` (per-issue history).
- Reply generator is a single function `_mock_sonar_ai_reply(issue, intent, user_text)` — swap to LlmChat later without touching routes/frontend.

All read endpoints serve static mock JSON; the workflow endpoints persist mutations in an in-memory dict `_SQ_ISSUE_STATE` keyed by issue key (resets on backend restart — intentional for the mock).

## Frontend env (`/app/frontend/.env`)
```
REACT_APP_BACKEND_URL=https://sonar-integration.preview.emergentagent.com
REACT_APP_API_URL=https://sonar-integration.preview.emergentagent.com/api
```
- `REACT_APP_BACKEND_URL` consumed by `src/lib/api.js` (general API + auth)
- `REACT_APP_API_URL` consumed by `src/hooks/useSonarQubeData.js` (SonarQube mock calls)

## Code Quality UI
- Route: `/code-quality`
- Page: `src/pages/CodeQuality.jsx`
- Sidebar nav entry: `data-testid="nav-code-quality"` (Code2 icon)
- Renders: header card (project + quality-gate badge), 6 metric cards (bugs / vulnerabilities / code smells / coverage% / duplications% / LOC), issues list, quality gate conditions

## What's Implemented (chronological)
- 2026-05-14 — Cloned triage-ai repo into `/app/triage-ai-integration/`
- 2026-05-14 — Mock SonarQube endpoints wired into `server.py`
- 2026-05-14 — `CodeQuality.jsx` page + `useSonarQubeData` hook + sidebar nav entry
- 2026-05-14 — Fixed `ajv-keywords` vs `ajv` version conflict on frontend; added `python-dotenv` to backend deps
- 2026-05-14 — Supervisor entries `triageai-backend` + `triageai-frontend` created
- 2026-05-14 — Fixed missing `REACT_APP_BACKEND_URL` in frontend `.env` (was blocking login)
- 2026-05-14 — `testing_agent_v3_fork` iter 5: 100% frontend pass on `/app/triage-ai-integration/test_reports/iteration_5.json`
- 2026-05-14 — **Workspace flattened**: deleted stale `/app/backend` + `/app/frontend` POC, moved `/app/triage-ai-integration/*` to `/app/` (preserving `.git`), updated supervisor config to point to `/app/backend` and `/app/frontend`. Result: `/app/.git` now points to `simransirsat/triage-ai` so Emergent's "Save to GitHub" works.

## Backlog / P1
- Replace localhost fallback in `useSonarQubeData.js` with strict env (`process.env.REACT_APP_API_URL`)
- Surface underlying axios error (status + message) in `useSonarQubeData` for easier debugging
- Verify operator label mapping in `CodeQuality.jsx` (`LESS_THAN` → `Must be ≥` vs `Must be ≤`) against intended UX spec
- Add `data-testid` attributes to Code Quality inner elements (`metric-{title}`, `qg-status`, `issue-{key}`, `refresh-btn`) for richer e2e tests

## Backlog / P2
- Split monolithic `server.py` (>700 lines) into route modules under `backend/routes/`
- Add backend pytest coverage for `/api/sonarqube/*` endpoints

## Known Mocks / Stubs
- **MOCKED**: All three `/api/sonarqube/*` endpoints serve static JSON. No live SonarQube/SonarCloud connection.

## GitHub Push
- Workspace is now a valid git repo at `/app` with `origin → https://github.com/simransirsat/triage-ai.git`.
- Click **"Save to GitHub"** in Emergent UI to push (recommended branch: feature branch since main is protected upstream).
