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

### Iteration 3 (2026-05-10) — Real Webhook Ingestion
- **Per-source ingest_token** (32-char hex) auto-generated on source creation; backfilled for legacy sources
- **Public `POST /api/sources/{id}/ingest`** — auth via `?token=` query OR `X-Ingest-Token` header. 401 wrong token, 403 disabled source, 404 missing source.
- **6 payload adapters** — cloudwatch (SNS ALARM/OK/INSUFFICIENT_DATA), datadog (alert_type), pagerduty (event.data.urgency), grafana/prometheus (Alertmanager multi-alert), custom passthrough. Severity normalized via `_norm_severity`.
- **`POST /api/sources/{id}/test`** (auth-required) — fires a curated sample payload through the same pipeline so users can verify wiring without a real monitoring tool.
- **Counters** — `ingest_count` + `last_ingested_at` track per-source activity.
- **Settings UI** — masked webhook URLs with reveal/copy/test buttons per source, live counter display.

## Backlog
### P1 (next)
- Refactor server.py (now ~950 lines) into modules (`routes/auth`, `routes/incidents`, `routes/sources`, `services/triage`, `services/webhook_adapters`)
- RBAC: gate sources/users mutations to admin/on-call only
- Per-source rate limiting + body-size cap on /ingest endpoint
- Dedup window on ingested alerts (same source+title+service within N seconds)
- AI-generated post-incident report when incident is resolved

### P2
- Real Slack/Teams notifications for SLA breaches and high-priority incidents (needs webhook URLs)
- Email digest for unattended alerts
- WebSocket-based real-time alert feed (replace 6s polling)
- Brute-force protection on /api/auth/login + per-IP rate limiting
- Markdown rendering in chat responses + CLI command copy buttons

### P3
- Multi-tenancy (org_id row-level isolation)
- SAML/OIDC SSO
- LLM cost dashboard + feedback loop (thumbs up/down on AI output)
- Pluggable correlation engine (DBSCAN / temporal / service-graph)
