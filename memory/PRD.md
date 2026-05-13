# TriageAI — Product Requirements Document

## Original Problem Statement
Build the TriageAI application as described in the spec PDF — an AI-Powered Incident Triage Engine for Cloud Operations. Stack: React (frontend) + FastAPI (backend).

## Architecture
- **Frontend**: React 19 + react-router-dom 7 + Tailwind + lucide-react + recharts + sonner
- **Backend**: FastAPI + motor (async MongoDB) + emergentintegrations (Claude Sonnet 4.5)
- **DB**: MongoDB collections — `users`, `alerts`, `incidents`, `triage_results`, `incident_chats`, `sources`
- **Auth**: JWT Bearer (24h), bcrypt hashed passwords, 4 seeded demo users
- **AI**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) via Emergent Universal LLM Key — used for both batch triage and per-incident chatbot

## User Personas
- **Admin** — full access including source mgmt
- **On-call SRE** — primary user; picks up incidents, drives resolution, uses AI copilot
- **Viewer** — read-only

## Implemented (current)
### Iteration 1 (2026-05-10)
- Alert ingestion / list / resolve / simulate endpoints
- Claude Sonnet 4.5 triage → priority, blast radius, MTTR, root causes (ranked, with confidence + supporting alerts), 3-phase remediation playbook with CLI commands, noise filter
- Incidents list + detail
- Analytics dashboard (totals, by-source, MTTR trend 7d, severity breakdown, top incidents)
- Settings page
- Terminal/SRE control-room dark UI per design guidelines (Chivo + JetBrains Mono)
- Sample data seeder

### Iteration 2 (2026-05-10)
- **JWT auth** — login screen with demo accounts, AuthProvider, protected routes, axios Bearer interceptor, logout
- **Monitoring sources CRUD** — add/list/toggle/delete sources from Settings (cloudwatch, datadog, pagerduty, grafana, prometheus, custom). 4 defaults seeded on startup.
- **Per-incident AI chatbot** — Claude Sonnet 4.5 with full incident context (alerts + triage), persisted history in `incident_chats`, locked when incident is resolved
- **Incident workflow** — pickup (auto-assigns + status→in_progress), add collaborators, post updates, mark resolved (closes linked alerts, locks chat). Activity log timeline.
- **My Incidents tabs** — mine / others / all on Incidents page
- **Unattended-alert SLA** — `/api/alerts/unattended` (>5 days), `UnattendedBanner` polls every 60s, demo "Age Alerts" button to fast-forward 3 alerts

## Test Credentials
See `/app/memory/test_credentials.md`. 4 users seeded: admin, sre1, sre2, viewer.

### Iteration 4 (2026-05-11) — Notifications + Theme Toggle
- **Notification Channels (admin-only CRUD)** — Slack, Microsoft Teams, Discord, Generic webhook, Email via Resend
- **Configurable triggers per channel** — `incident_created` (P1/P2), `sla_breach` (>5d), `incident_resolved`
- **Dispatcher** — `dispatch_event()` fires all enabled matching channels concurrently via `asyncio.create_task`; per-call status saved to channel (`last_status`) + audit log (`notification_log`)
- **SLA dedup** — first time an unattended alert is detected it dispatches a breach event; subsequent calls skip it via per-alert marker
- **RBAC** — `require_admin` dependency gates create/update/delete/test
- **Theme toggle** — Sun/Moon button in header; light theme overrides via `html[data-theme="light"]` CSS rules; persisted to `localStorage` (`triage_theme`); default dark

### Iteration 5 (2026-05-12) — F-01 Deployment Change Correlation
- **`cicd_tools` & `deployment_events` collections** — Fernet-encrypted API tokens (JWT_SECRET-derived key), service watchlists, sync counters.
- **Adapter pattern** — `BaseCICDAdapter` interface with real `GitHubActionsAdapter` (workflow_runs + commit/files via GitHub REST), `MockAdapter` (synthetic deployments for demo), and stubs for GitLab/CircleCI/ArgoCD.
- **`DeploymentCorrelator`** — confidence = 0.5·time + 0.35·service_match + 0.15·file_relevance. Labels: high ≥ 0.7, medium ≥ 0.4, else low.
- **Endpoints** — `GET/POST/PATCH/DELETE /api/cicd/tools` (admin CRUD), `POST /api/cicd/tools/{id}/test`, `POST /api/cicd/sync-all`, `GET /api/cicd/deployments`, `GET /api/incidents/{id}/deployments?window_minutes&confidence_min`.
- **Background sync** — asyncio loop calls `CICDToolService.sync_all()` every 60s; idempotent via `external_id`.
- **Claude prompt enrichment** — `/api/triage` correlates deployments before LLM call and prepends a `RECENT DEPLOYMENTS` block to the user message when confidence ≥ 0.3; response now includes a `deployments` array.
- **Frontend** — `DeploymentCard` rendered at top of Triage Panel + Incident Detail with confidence badge, deployer avatar, time delta, top-3 changed files (click to copy / expand for diff), PR + CI links, one-click Rollback button (clipboard).
- **Settings → CI/CD Integrations** — admin UI to register/edit/test/toggle tools per provider type; auto-seeds one Mock tool on first startup so the full flow demos without real credentials.


- **Per-source ingest_token** (32-char hex) auto-generated on source creation; backfilled for legacy sources
- **Public `POST /api/sources/{id}/ingest`** — auth via `?token=` query OR `X-Ingest-Token` header. 401 wrong token, 403 disabled source, 404 missing source.
- **6 payload adapters** — cloudwatch (SNS ALARM/OK/INSUFFICIENT_DATA), datadog (alert_type), pagerduty (event.data.urgency), grafana/prometheus (Alertmanager multi-alert), custom passthrough. Severity normalized via `_norm_severity`.
- **`POST /api/sources/{id}/test`** (auth-required) — fires a curated sample payload through the same pipeline so users can verify wiring without a real monitoring tool.
- **Counters** — `ingest_count` + `last_ingested_at` track per-source activity.
- **Settings UI** — masked webhook URLs with reveal/copy/test buttons per source, live counter display.

## Backlog
### P1 (next)
- Refactor server.py (now ~1800+ lines) into modules (`routes/auth`, `routes/incidents`, `routes/sources`, `routes/notifications`, `routes/cicd`, `services/triage`, `services/webhook_adapters`, `services/cicd_adapters`, `services/notifications`)
- RBAC: gate sources mutations + /auth/users to admin/on-call only
- Per-source rate limiting + body-size cap on /ingest endpoint
- Dedup window on ingested alerts (same source+title+service within N seconds)
- AI-generated post-incident report when incident is resolved (auto-drafted summary + action items shareable as public post-mortem URL)
- F-01: implement real GitLab / CircleCI / ArgoCD adapters (stubs already in place)
- F-01: surface "Rollback executed" feedback loop (track whether the suggested rollback was actually run, to improve future confidence scoring)

### P2
- Markdown rendering in chat responses + CLI command copy buttons
- Email digest for unattended alerts (using existing email channel)
- WebSocket-based real-time alert feed (replace 6s polling)
- Brute-force protection on /api/auth/login + per-IP rate limiting
- Per-incident notification routing (notify only the assignee's preferred channels)

### P3
- Multi-tenancy (org_id row-level isolation)
- SAML/OIDC SSO
- LLM cost dashboard + feedback loop (thumbs up/down on AI output)
- Pluggable correlation engine (DBSCAN / temporal / service-graph)
