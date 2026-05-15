# TriageAI – PRD

## Original problem statement
Resolve merge conflicts for PR #4 of `Alston-Dias/triage-ai`
(<https://github.com/Alston-Dias/triage-ai/pull/4>) and make sure that nothing
breaks. Test everything.

The PR (`simransirsat:sonar-feature` → `Alston-Dias:main`) adds a SonarQube
Code Quality dashboard with AI chat. `main` had meanwhile gained F-02
Predictive Triage. Both features must coexist after the merge.

## Architecture
- **Backend** — FastAPI single-file app (`/app/backend/server.py`, 3.3k LOC).
  Routes registered under `/api`. MongoDB via motor. Claude via
  `emergentintegrations`. WebSocket `/api/ws/predictive-alerts`.
- **Frontend** — React 18 + CRA + craco + Tailwind + lucide-react.
  Routes: `/` (Live Triage), `/incidents`, `/incidents/:id`, `/predictive`,
  `/analytics`, `/code-quality`, `/settings`.
- **Auth** — JWT (HS256, 24h), bcrypt password hashes. 4 seeded users.

## Conflicts resolved in this merge
| File | Strategy |
| ---- | -------- |
| `.emergent/emergent.yml` | Kept HEAD metadata |
| `.gitignore` | Deduped both sides into a clean canonical list |
| `backend/server.py` | Kept HEAD imports (WebSocket needed) + **both** F-02 Predictive block and SonarQube block |
| `backend_test.py` | Kept HEAD's F-02 tests; PR's Sonar tests preserved as `backend_test_sonar.py` |
| `frontend/src/App.js` | Imported and routed both `PredictiveDashboard` and `CodeQuality` |
| `frontend/src/components/Layout.jsx` | Merged icon imports (`TrendingUp` + `Code2`); NAV already had both entries |
| `test_result.md` | Kept full history blocks from both sides |

## Features (post-merge)
### F-02 Predictive Triage (HEAD)
- 5 monitored services × 5 metric types, 4h synthetic history seeded in `db.metrics`.
- IsolationForest anomaly detection → risk score 0–100 + ETA + Claude recommendation.
- REST: `GET /api/predictive-services/summary`, `GET /api/predictive-incidents`,
  `POST /api/predictive-triage`, `GET .../trend`, `PATCH .../acknowledge`,
  `PATCH .../resolve`.
- WebSocket: `wss://.../api/ws/predictive-alerts?token=<JWT>` — emits `snapshot`
  on connect and `prediction.new` on each run.

### SonarQube Code Quality + AI Chat (PR)
- Mock SonarQube dataset (4 issues across 4 components).
- REST: `GET /api/sonarqube/summary`, `GET /api/sonarqube/issues`,
  `GET .../{key}`, `POST .../{key}/claim`, `POST .../{key}/assign`,
  `PATCH .../{key}/status`, `GET /api/sonarqube/quality-gate`,
  `POST .../{key}/generate-fix`, `GET|POST .../{key}/comments`,
  `POST .../{key}/chat` (5 intents: Explain Rule, Generate Fix,
  Alternative Fix, Write Test, PR Description).

## Test status (iteration_8)
- Backend pytest: **27/27 PASS** (`/app/backend/tests/test_post_merge_pr4.py`).
- Frontend Playwright: **100%** of critical post-merge flows verified.
- **No regressions** introduced by the merge.

## What's been implemented
- 2026-05-15 — Resolved 7 merge conflicts from PR #4; both Predictive Triage
  and SonarQube Code Quality features verified working end-to-end.

## Backlog / Future
- (P2) Split `server.py` into routers (`routers/predictive.py`,
  `routers/sonarqube.py`) — file is now 3.3k lines.
- (P2) Tighten auth on `/api/sonarqube/summary|issues|quality-gate` — currently
  publicly readable.
- (P3) Add `service-risk-card-{name}` testids on Predictive cards.
- (P3) Add `aria-describedby` to Radix `DialogContent` (a11y).
- (P3) Promote `_SQ_ISSUE_STATE` from in-process dict to Mongo collection.

## Next tasks
1. (Optional) Push resolved branch back via "Save to GitHub" – user choice.
2. (Optional) Address the P2 backlog items above before next feature work.

## Code Quality v2 (May 2026)

- **GitHub URL scan**: clone a public or private (PAT-injected) repo, AI-analyze up to 30 source files with Claude Sonnet 4.5 in the background, store SonarQube-style issues per scan.
- **.zip upload scan**: 50 MB / 2000 file cap, same analyzer pipeline.
- **External scanner integrations**: SonarQube, SonarCloud, Snyk, GitHub Advanced Security, Semgrep Cloud, and a generic Custom provider. Each integration is enable/disable-able and deletable. Sync pulls live issues from the external dashboard.
- **AI Fix**: per-issue, Claude returns `{explanation, patched_file, unified diff, test_hint}`. If the user gives a GitHub repo+PAT, we auto-fetch the affected file so the patched output is real.
- **Demo seeder**: `POST /api/code-quality/demo/seed?reset=true|false` populates 3 integrations (one disabled), 5 scans, 17 issues, and one pre-baked AI fix for client demos.

Implemented in `backend/code_quality_v2.py` (router mounted at `/api/code-quality/*`) and `frontend/src/components/CodeQualityScansPanel.jsx`. Existing static SonarQube mock is preserved underneath, clearly labeled "Demo project · static sonarqube dashboard".
