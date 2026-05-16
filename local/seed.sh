#!/usr/bin/env bash
# Seeds dummy data via authenticated API calls. The backend's startup hook
# already creates demo users + sources; this script populates alerts,
# notification log entries, and ages a few alerts so the "unattended"
# banner has something to show.
set -Eeuo pipefail

API="${API:-http://localhost:8001/api}"
EMAIL="${EMAIL:-admin@triage.ai}"
PASSWORD="${PASSWORD:-admin123}"

GRN='\033[0;32m'; YLW='\033[0;33m'; BLU='\033[0;34m'; RED='\033[0;31m'; BLD='\033[1m'; CLR='\033[0m'
log()  { printf "${BLU}${BLD}»${CLR} %s\n" "$*"; }
ok()   { printf "${GRN}✓${CLR} %s\n" "$*"; }
warn() { printf "${YLW}!${CLR} %s\n" "$*"; }
die()  { printf "${RED}✗${CLR} %s\n" "$*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || die "curl is required."
if ! command -v jq >/dev/null 2>&1; then
    warn "jq not found — falling back to python for JSON parsing"
    JQ_CMD='python -c "import sys,json; print(json.load(sys.stdin)[sys.argv[1]])"'
else
    JQ_CMD=""
fi

# wait for /api/ up to 30s
for i in $(seq 1 30); do
    if curl -fsS "$API/" >/dev/null 2>&1; then break; fi
    sleep 1
    [ "$i" = 30 ] && die "Backend at $API is not reachable."
done

log "Logging in as $EMAIL …"
RESP=$(curl -fsS -X POST "$API/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}") \
    || die "Login failed. Has the backend finished its first-run user seeding?"
if [ -n "$JQ_CMD" ]; then
    TOKEN=$(echo "$RESP" | jq -r '.access_token')
else
    TOKEN=$(echo "$RESP" | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
fi
[ -z "$TOKEN" ] || [ "$TOKEN" = "null" ] && die "Could not extract access token from login response."
ok "Auth token obtained"

AUTH_H="Authorization: Bearer $TOKEN"

log "Seeding sample alerts (POST /api/seed)…"
curl -fsS -X POST "$API/seed" -H "$AUTH_H" >/dev/null && ok "Sample alerts seeded"

log "Ageing 3 alerts to 6 days old (for unattended demo)…"
curl -fsS -X POST "$API/demo/age-alerts" -H "$AUTH_H" >/dev/null && ok "Unattended banner armed"

log "Simulating 4 fresh alerts…"
for _ in 1 2 3 4; do
    curl -fsS -X POST "$API/alerts/simulate" -H "$AUTH_H" >/dev/null || true
done
ok "4 simulated alerts pushed"

log "Adding a couple of demo notification channels (best-effort)…"
curl -fsS -X POST "$API/notifications/channels" -H "$AUTH_H" -H 'Content-Type: application/json' \
     -d '{"name":"#sre-alerts","type":"slack","config":{"webhook_url":"https://hooks.slack.com/services/T000/B000/dummy"},"events":["incident_created","alert_unattended"]}' \
     >/dev/null 2>&1 && ok "Slack channel added" || warn "Slack channel skipped (likely already exists)"
curl -fsS -X POST "$API/notifications/channels" -H "$AUTH_H" -H 'Content-Type: application/json' \
     -d '{"name":"On-call email","type":"email","config":{"to":"oncall@example.com"},"events":["incident_created"]}' \
     >/dev/null 2>&1 && ok "Email channel added" || warn "Email channel skipped (likely already exists)"

echo
printf "${GRN}${BLD}Seed complete.${CLR}  Visit ${BLU}http://localhost:3000${CLR} and log in as ${BLD}sre1@triage.ai${CLR} / ${BLD}sre123${CLR}.\n\n"
