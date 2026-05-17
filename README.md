# TriageAI – AI-Powered SRE Console

> An end-to-end Site Reliability Engineering platform that ingests live alerts,
> auto-clusters them into incidents, runs predictive ML against service
> metrics, scans your codebase for quality issues, and lets on-call engineers
> chat with Claude to find the root cause faster.

---

## 📦 Documentation & Media

Large binary docs live under [`/documentation`](./documentation/). Once you
drop your slide deck and demo video into that folder using the canonical
filenames, the links below will resolve automatically.

| Asset                | Path                                                                          | Description                                          |
| -------------------- | ----------------------------------------------------------------------------- | ---------------------------------------------------- |
| 🎤 Presentation       | [`documentation/TriageAI_Presentation.pptx`](./documentation/TriageAI_Presentation.pptx) | **Latest pitch deck** (upload here)                  |
| 🎬 Demo video         | [`documentation/TriageAI_Demo.mp4`](./documentation/TriageAI_Demo.mp4)               | **Walk-through video** (upload here)                 |
| 📑 Spec PDF           | [`documentation/TriageAI_Specification_v2.pdf`](./documentation/TriageAI_Specification_v2.pdf) | Full functional / technical specification           |
| 🗒️ Original pitch     | [`documentation/TriageAI_Pitch.pptx`](./documentation/TriageAI_Pitch.pptx)           | The pitch deck shipped with the initial repo        |

> See [`documentation/README.md`](./documentation/README.md) for naming
> conventions and upload instructions.

---

## 🧠 What the product does (60-second tour)

1. **Live Triage** – Alerts stream in from CloudWatch / Datadog / PagerDuty /
   Grafana (or via a generic ingest webhook). The Claude-powered triage
   engine clusters related alerts, ranks probable root causes, and produces
   an actionable runbook.
2. **Incidents** – Every triage run materialises an incident with chat,
   collaborators, deployment correlation, and resolution timeline.
3. **Predictive Triage (F-02)** – `IsolationForest` continuously scores 5
   services across 5 metric types (CPU, memory, latency, error rate, traffic)
   and pushes alerts *before* an outage via WebSocket.
4. **Code Quality** – Two modes:
   - **Static SonarQube dashboard** (mock dataset, 4 issues, AI fix chat).
   - **Code Quality v2** – clone a public/private GitHub repo or upload a
     `.zip`, Claude analyses up to 30 files, surfaces issues, and produces
     `{explanation, patched_file, unified diff, test_hint}` AI-fixes.
5. **External scanners** – Plug-in support for SonarQube, SonarCloud, Snyk,
   GitHub Advanced Security, Semgrep Cloud, and a generic Custom provider.
6. **Analytics** – MTTR, alerts-per-source, severity mix, top noisy services.
7. **Settings** – Manage sources, notification channels, CI/CD tools, themes.

---

## 🏗️ Architecture

```
┌──────────────────────────────┐         ┌──────────────────────────────┐
│  Frontend (React 19 + CRA)   │  HTTPS  │   Backend (FastAPI + Motor)  │
│  Tailwind + Radix + Recharts │ ◄─────► │   /api/*  (single-process)   │
│  React-Router v7             │   WS    │   /api/ws/predictive-alerts  │
└──────────────────────────────┘         └──────────────┬───────────────┘
                                                        │ MongoDB
                                                        ▼
                                                ┌──────────────┐
                                                │   MongoDB    │
                                                │ (motor 3.3)  │
                                                └──────────────┘
                                                        │
                                                        ▼
                                          ┌──────────────────────────┐
                                          │ Claude Sonnet 4.5        │
                                          │ via emergentintegrations │
                                          └──────────────────────────┘
```

| Layer       | Tech                                                                          |
| ----------- | ----------------------------------------------------------------------------- |
| Frontend    | React 19, react-router v7, Tailwind 3, Radix UI, lucide-react, recharts, axios |
| Backend     | FastAPI 0.110, motor 3.3, pydantic 2, JWT (PyJWT), bcrypt, scikit-learn 1.5    |
| LLM         | Claude Sonnet 4.5 via `emergentintegrations`                                  |
| ML          | `IsolationForest` (scikit-learn) for anomaly detection                        |
| Auth        | JWT HS256, 24 h TTL, bcrypt password hashes                                   |
| Realtime    | Native FastAPI `WebSocket` at `/api/ws/predictive-alerts`                     |
| Process mgr | supervisord (separate frontend / backend / mongodb units)                     |

---

## 📁 Repository layout

```
/app
├── backend/
│   ├── server.py              # FastAPI app, all routes under /api  (3.3k LOC)
│   ├── code_quality_v2.py     # /api/code-quality/* router          (1.3k LOC)
│   ├── llm_provider.py        # LlmChat factory + active-model resolver
│   ├── requirements.txt
│   └── tests/                 # pytest suites (27 passing)
│
├── frontend/
│   ├── src/
│   │   ├── App.js             # Router tree
│   │   ├── pages/             # Dashboard, Incidents, IncidentDetail,
│   │   │                      # Analytics, CodeQuality, Settings, Login
│   │   ├── components/        # Layout, TriagePanel, AlertFeed,
│   │   │                      # IncidentChat, IssueAIChat,
│   │   │                      # CodeQualityScansPanel, ...
│   │   ├── components/predictive/  # PredictiveDashboard + cards
│   │   ├── components/ui/     # Radix-based primitives (shadcn-style)
│   │   ├── hooks/             # useActiveModel, useSonarQubeData, ...
│   │   └── lib/               # api.js, auth.js, codeQualityApi.js, ...
│   ├── package.json
│   └── tailwind.config.js
│
├── documentation/             # PPTX / PDF / MP4 (this is where uploads go)
│
├── docker/                    # Container build (entrypoint, seed, supervisord)
├── docker-compose.yml
├── Dockerfile
└── README.md                  # ← you are here
```

---

## 🔌 Backend – module-by-module

### `backend/server.py`  *(single-file monolith)*

Sections, in order:

| Section                          | Lines        | What it does                                              |
| -------------------------------- | ------------ | --------------------------------------------------------- |
| Imports / env loading            | 1–48         | Loads `backend/.env` + repo-root `.env`; opens Mongo.     |
| Pydantic models                  | 51–235       | `Alert`, `Incident`, `TriageRequest`, `Source`, `Channel`, `Metric`, `PredictiveIncident`, `SonarQubeIssue`, … |
| Auth helpers                     | 236–256      | `hash_password`, `verify_password`, `create_token`, `get_current_user`, `admin_only`. |
| Seed users + startup hook        | 259–294      | Inserts the 4 demo users if missing, seeds default sources. |
| `/api/auth/*`                    | 298–316      | `POST /login`, `GET /me`, `GET /users`.                   |
| Alerts                           | 345–406      | Ingest, list, unattended, resolve, bulk-resolve.          |
| Incidents                        | 408–500      | List / get / pickup / collaborators / updates / resolve.  |
| Triage engine                    | 552–700      | Clusters alerts and asks Claude for root cause + runbook. |
| Incident chat                    | 683–740      | Per-incident Claude chat with persistent history.         |
| Sources                          | 742–940      | Source CRUD, ingest, connectivity test.                   |
| Notifications                    | 1024–1078    | Channel CRUD, send-test, audit log.                       |
| Analytics                        | 1079–1140    | MTTR, top services, severity mix.                         |
| Demo / seed helpers              | 1143–1180    | Reset DB, age alerts, simulate noise.                     |
| CI/CD tools & deployments        | 1694–1770    | Connect Jenkins / GitHub Actions / etc., correlate deploys. |
| **F-02 Predictive Triage**       | 2200–2400    | `POST /predictive-triage`, services summary, trend, acknowledge, resolve, **WebSocket** broadcast. |
| **SonarQube Code Quality (mock)**| 2588–3300    | Issues list / detail, claim / assign / status, quality-gate, generate-fix, comments, AI chat (5 intents). |

### `backend/code_quality_v2.py`  *(mounted at `/api/code-quality/*`)*

| Endpoint                                                       | Purpose                                          |
| -------------------------------------------------------------- | ------------------------------------------------ |
| `POST /scans/github`                                           | Clone & scan a public / PAT-injected GitHub repo |
| `POST /scans/upload`                                           | Upload a `.zip` (≤50 MB / 2000 files) & scan     |
| `GET /scans`, `GET /scans/{id}`, `DELETE /scans/{id}`          | List / fetch / delete scan jobs                  |
| `GET /scans/{id}/issues`                                       | Issues produced by a scan                        |
| `GET|POST /integrations`, `PATCH|DELETE /integrations/{id}`    | External scanner integrations CRUD               |
| `POST /integrations/{id}/sync`                                 | Pull live issues from the external dashboard     |
| `POST /issues/{id}/fix`, `GET /issues/{id}`                    | Generate an AI fix, fetch enriched issue         |
| `POST /demo/seed?reset=true|false`                             | Populate demo integrations / scans / issues      |

### `backend/llm_provider.py`

Wraps `emergentintegrations.LlmChat`, exposes:

- `get_chat(session_id, system_message)` → an LlmChat configured for the
  currently-active model.
- `llm_is_configured()` → bool, honours `MODEL` / `GATEWAY_*` env vars.
- `active_model()` → string used by the UI in the model picker.

### Environment variables

| Variable                    | Required | Notes                                                    |
| --------------------------- | -------- | -------------------------------------------------------- |
| `MONGO_URL`                 | ✅        | Local mongo, leave as shipped.                           |
| `DB_NAME`                   | ✅        | `triageai` by default.                                   |
| `JWT_SECRET`                | ✅        | 32+ char random string.                                  |
| `EMERGENT_LLM_KEY`          | ✅        | Universal LLM key (Claude / OpenAI / Gemini).            |
| `MODEL`                     | optional | Override default model (e.g. `claude-sonnet-4-5`).       |
| `GATEWAY_BASE_URL`          | optional | Custom LLM gateway base.                                 |
| `GATEWAY_API_KEY`           | optional | Custom LLM gateway key (alternative to `EMERGENT_LLM_KEY`).|
| `RESEND_API_KEY`            | optional | Email notifications.                                     |
| `FERNET_KEY`                | optional | Used to encrypt source secrets at rest.                  |

---

## 🎨 Frontend – module-by-module

### `src/App.js`

```jsx
<ThemeProvider>
  <AuthProvider>
    <ActiveModelProvider>
      <BrowserRouter>
        Routes:
          /login                        → <Login />
          /                             → <Dashboard />            (Live Triage)
          /incidents                    → <Incidents />
          /incidents/:id                → <IncidentDetail />
          /predictive                   → <PredictiveDashboard />
          /analytics                    → <Analytics />
          /code-quality                 → <CodeQuality />
          /settings                     → <Settings />
      </BrowserRouter>
    </ActiveModelProvider>
  </AuthProvider>
</ThemeProvider>
```

All non-`/login` routes are guarded by `<ProtectedRoute>`, which redirects to
`/login` if no JWT is present.

### Pages

| Page              | Highlights                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------------- |
| `Dashboard.jsx`   | Live alert feed (`AlertFeed`), unattended banner, multi-select triage button (`TriagePanel`). |
| `Incidents.jsx`   | Filterable list of incidents, pickup / resolve actions.                                     |
| `IncidentDetail.jsx` | Timeline, collaborators, root-cause cards, AI chat (`IncidentChat`), correlated deployments. |
| `Analytics.jsx`   | MTTR, severity breakdown, top noisy services (Recharts).                                    |
| `CodeQuality.jsx` | Two tabs: SonarQube mock dashboard + Code Quality v2 (`CodeQualityScansPanel`).            |
| `Settings.jsx`    | Sources, notification channels, CI/CD tools, theme, model picker.                          |
| `Login.jsx`       | Email/password form, seeds demo creds in placeholder.                                       |

### Key components

| Component                       | Role                                                                   |
| ------------------------------- | ---------------------------------------------------------------------- |
| `Layout.jsx`                    | Sidebar nav, theme toggle, logout, unattended banner mount point.       |
| `AlertFeed.jsx`                 | Streaming alerts table with severity badges.                            |
| `TriagePanel.jsx`               | Triage submit + result viewer (root-cause cards + runbook).             |
| `IncidentChat.jsx`              | Per-incident chat, persists to `/api/incidents/:id/chat`.               |
| `IssueAIChat.jsx`               | SonarQube issue chat with the 5 quick-action intents.                   |
| `IssueDetailSheet.jsx`          | Side sheet for SonarQube issue details.                                 |
| `CodeQualityScansPanel.jsx`     | New (v2) scans dashboard: GitHub URL, ZIP upload, scan list, AI fix.    |
| `FixPreviewModal.jsx`           | Diff viewer for AI-generated patches.                                   |
| `SonarSummaryBar.jsx`           | KPI strip on the SonarQube tab.                                         |
| `predictive/PredictiveDashboard.jsx` | Service risk cards + WebSocket alert feed.                         |
| `predictive/*`                  | Service-card, ETA gauge, recommendation panel.                          |
| `CICDToolsSettings.jsx`         | Jenkins / GitHub Actions / GitLab CI connector form.                    |
| `NotificationsSettings.jsx`     | Slack / email / webhook channels + send-test.                           |
| `UnattendedBanner.jsx`          | Top banner showing alerts no engineer has picked up.                    |

### `src/lib/`

| File                    | Responsibility                                                  |
| ----------------------- | --------------------------------------------------------------- |
| `api.js`                | Axios instance, `REACT_APP_BACKEND_URL`, auth-header injector.  |
| `auth.js`               | `AuthProvider`, `useAuth`, login / logout / refresh-on-mount.   |
| `codeQualityApi.js`     | Thin wrapper around `/api/code-quality/*`.                      |
| `theme.js`              | Light/dark theme provider (default = dark).                     |
| `severity.js`, `format.js`, `utils.js` | Pure helpers (color maps, time-ago, classNames). |
| `preserveProxyRouting.js` | Keeps `/api` prefix on dev / prod / CRA proxy.                |

### `src/hooks/`

- `useActiveModel.jsx` — globally tracks which LLM model the user picked
  (`claude-sonnet-4-5`, `gpt-4o`, `gemini-2.5-pro`, …).
- `useSonarQubeData.js` — fetches summary, issues, quality-gate, comments.
- `use-toast.js` — Sonner toast helper.

---

## 🔑 API surface (cheat-sheet)

> All routes are prefixed with `/api`. JWT must be sent as `Authorization:
> Bearer <token>` unless noted.

### Auth
- `POST /api/auth/login` `{ email, password }` → `{ access_token, user }`
- `GET  /api/auth/me`
- `GET  /api/auth/users`  (any authed user)

### Alerts & incidents
- `POST  /api/alerts/ingest`
- `GET   /api/alerts` / `GET /api/alerts/unattended`
- `PATCH /api/alerts/{alert_id}/resolve`
- `POST  /api/alerts/resolve-bulk`
- `GET   /api/incidents` / `GET /api/incidents/{id}`
- `POST  /api/incidents/{id}/pickup` / `…/collaborators` / `…/updates` / `…/resolve`
- `GET|POST /api/incidents/{id}/chat`
- `POST  /api/triage`

### Sources & notifications
- `GET|POST /api/sources`, `PATCH|DELETE /api/sources/{id}`
- `POST /api/sources/{id}/ingest`, `POST /api/sources/{id}/test`
- `GET|POST /api/notifications/channels`, `PATCH|DELETE /api/notifications/channels/{id}`
- `POST /api/notifications/channels/{id}/test`
- `GET  /api/notifications/log`

### Predictive triage (F-02)
- `POST  /api/predictive-triage`
- `GET   /api/predictive-services/summary`
- `GET   /api/predictive-incidents`
- `GET   /api/predictive-incidents/{id}/trend`
- `PATCH /api/predictive-incidents/{id}/acknowledge`
- `PATCH /api/predictive-incidents/{id}/resolve`
- **WS** `/api/ws/predictive-alerts?token=<JWT>` (emits `snapshot` then `prediction.new`)

### SonarQube (static demo)
- `GET   /api/sonarqube/summary`
- `GET   /api/sonarqube/issues`, `GET /api/sonarqube/issues/{key}`
- `POST  /api/sonarqube/issues/{key}/claim`
- `POST  /api/sonarqube/issues/{key}/assign`
- `PATCH /api/sonarqube/issues/{key}/status`
- `GET   /api/sonarqube/quality-gate`
- `POST  /api/sonarqube/issues/{key}/generate-fix`
- `GET|POST /api/sonarqube/issues/{key}/comments`
- `GET|POST /api/sonarqube/issues/{key}/chat`
- `GET   /api/sonarqube/trend`
- `GET   /api/sonarqube/config`

### Code Quality v2 (`/api/code-quality/*`)
- Scans: `POST /scans/github`, `POST /scans/upload`, `GET /scans`,
  `GET /scans/{id}`, `DELETE /scans/{id}`, `GET /scans/{id}/issues`.
- Integrations: `GET|POST /integrations`, `PATCH|DELETE /integrations/{id}`,
  `POST /integrations/{id}/sync`.
- Issues: `POST /issues/{id}/fix`, `GET /issues/{id}`.
- Demo: `POST /demo/seed?reset=true|false`.

### Analytics & CI/CD
- `GET  /api/analytics/summary`
- `GET|POST /api/cicd/tools`, `PATCH|DELETE /api/cicd/tools/{id}`,
  `POST /api/cicd/tools/{id}/test`, `POST /api/cicd/sync-all`
- `GET  /api/cicd/deployments`, `GET /api/incidents/{id}/deployments`

---

## 👥 Seeded demo users

| Email             | Password   | Role     |
| ----------------- | ---------- | -------- |
| admin@triage.ai   | admin123   | admin    |
| sre1@triage.ai    | sre123     | on-call  |
| sre2@triage.ai    | sre123     | on-call  |
| viewer@triage.ai  | viewer123  | viewer   |

(Seeded on backend startup, hashed with bcrypt.)

---

## 🚀 Running locally

```bash
# 1. Start everything via supervisor (already configured in this container)
sudo supervisorctl restart all
sudo supervisorctl status

# 2. Backend hot-reloads on file save; frontend runs CRA + craco
#    Backend  → http://localhost:8001  (proxied through /api)
#    Frontend → http://localhost:3000

# 3. Tail logs if anything misbehaves
tail -n 200 /var/log/supervisor/backend.*.log
tail -n 200 /var/log/supervisor/frontend.*.log
```

For a fully containerised setup see [`DEPLOY_DOCKER.md`](./DEPLOY_DOCKER.md)
and [`LOCAL_SETUP.md`](./LOCAL_SETUP.md).

---

## 🧪 Tests

- **Backend pytest** — `cd backend && pytest`   → 27 / 27 PASS
  (`backend/tests/test_post_merge_pr4.py` covers the merged Predictive +
  SonarQube surface).
- **Frontend Playwright** — driven by the auto-testing agent; 100 % of
  critical post-merge flows verified in iteration 8.

---

## 🗺️ Roadmap / backlog

- (P2) Split `server.py` into routers (`routers/predictive.py`,
  `routers/sonarqube.py`).
- (P2) Tighten auth on `/api/sonarqube/summary|issues|quality-gate`
  (currently publicly readable).
- (P3) Add `service-risk-card-{name}` testids on Predictive cards.
- (P3) Add `aria-describedby` to Radix `DialogContent` for a11y.
- (P3) Promote `_SQ_ISSUE_STATE` from in-process dict to a Mongo collection.

---

## 📜 License & credits

Built on the Emergent stack. LLM integrations via
[`emergentintegrations`](https://pypi.org/project/emergentintegrations/).
Anomaly detection via `scikit-learn`. UI primitives from Radix and
[shadcn/ui](https://ui.shadcn.com/).
