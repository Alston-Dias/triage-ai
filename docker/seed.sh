#!/usr/bin/env bash
# Seeds dummy data into TriageAI on first boot. Idempotent: leaves a flag
# file in /data/db so subsequent container restarts skip the seed step.
set -Eeuo pipefail

FLAG_FILE=/data/db/.seeded
API="http://127.0.0.1:${PORT:-8001}/api"
EMAIL=admin@triage.ai
PASSWORD=admin123

log() { echo "[seeder] $*"; }

if [ -f "$FLAG_FILE" ]; then
    log "already seeded ("$FLAG_FILE" exists) — skipping."
    exit 0
fi

log "waiting for backend at $API …"
for i in $(seq 1 90); do
    if curl -fsS "$API/" >/dev/null 2>&1; then
        log "backend is up."
        break
    fi
    sleep 1
    if [ "$i" = 90 ]; then
        log "backend never came up in 90s, giving up."
        exit 1
    fi
done

# The backend's startup hook already seeds users + integration sources. We
# still need to call /api/seed for sample alerts. Retry login for ~30s since
# the startup hook runs asynchronously on first boot.
for i in $(seq 1 30); do
    RESP=$(curl -fsS -X POST "$API/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" 2>/dev/null || true)
    if echo "$RESP" | jq -e '.access_token' >/dev/null 2>&1; then
        TOKEN=$(echo "$RESP" | jq -r '.access_token')
        log "got auth token."
        break
    fi
    sleep 1
    if [ "$i" = 30 ]; then
        log "could not log in as $EMAIL after 30 retries (token never returned). Continuing without sample data."
        touch "$FLAG_FILE"
        exit 0
    fi
done

AUTH="Authorization: Bearer $TOKEN"

log "seeding sample alerts (/api/seed)…"
curl -fsS -X POST "$API/seed"            -H "$AUTH" >/dev/null && log "  ✓ sample alerts"

log "ageing 3 alerts to 6 days old (/api/demo/age-alerts)…"
curl -fsS -X POST "$API/demo/age-alerts" -H "$AUTH" >/dev/null && log "  ✓ unattended banner armed"

log "simulating 4 fresh alerts…"
for _ in 1 2 3 4; do
    curl -fsS -X POST "$API/alerts/simulate" -H "$AUTH" >/dev/null || true
done
log "  ✓ 4 fresh alerts pushed"

log "adding demo notification channels (best-effort)…"
curl -fsS -X POST "$API/notifications/channels" -H "$AUTH" -H 'Content-Type: application/json' \
     -d '{"name":"#sre-alerts","type":"slack","config":{"webhook_url":"https://hooks.slack.com/services/T000/B000/dummy"},"events":["incident_created","alert_unattended"]}' \
     >/dev/null 2>&1 && log "  ✓ slack channel" || log "  ~ slack channel skipped"
curl -fsS -X POST "$API/notifications/channels" -H "$AUTH" -H 'Content-Type: application/json' \
     -d '{"name":"On-call email","type":"email","config":{"to":"oncall@example.com"},"events":["incident_created"]}' \
     >/dev/null 2>&1 && log "  ✓ email channel" || log "  ~ email channel skipped"

touch "$FLAG_FILE"
log "done. seed flag written to $FLAG_FILE."
