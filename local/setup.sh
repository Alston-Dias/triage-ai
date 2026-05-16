#!/usr/bin/env bash
# =============================================================================
# TriageAI · Local Setup (macOS / Linux / WSL)
# Idempotent: safe to re-run. Installs everything required to run the app
# locally and seeds dummy data.
# =============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_DIR="$SCRIPT_DIR/.run"
LOG_DIR="$RUN_DIR/logs"
VENV_DIR="$REPO_DIR/backend/.venv"

mkdir -p "$RUN_DIR" "$LOG_DIR"

# ---------- pretty output ----------
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'; BLU='\033[0;34m'; BLD='\033[1m'; CLR='\033[0m'
log()  { printf "${BLU}${BLD}»${CLR} %s\n" "$*"; }
ok()   { printf "${GRN}✓${CLR} %s\n" "$*"; }
warn() { printf "${YLW}!${CLR} %s\n" "$*"; }
err()  { printf "${RED}✗${CLR} %s\n" "$*" >&2; }
die()  { err "$*"; exit 1; }

trap 'err "Setup failed on line $LINENO. Check $LOG_DIR for details."' ERR

echo
printf "${BLD}╭───────────────────────────────────────────────╮${CLR}\n"
printf "${BLD}│  TriageAI · Local Setup                        │${CLR}\n"
printf "${BLD}╰───────────────────────────────────────────────╯${CLR}\n\n"

# =============================================================================
# 1. PREREQUISITE CHECKS
# =============================================================================
log "Checking prerequisites…"

# --- Python --------------------------------------------------------------
PY_BIN=""
for candidate in python3.11 python3.12 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        v=$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
        major=$(echo "$v" | cut -d. -f1); minor=$(echo "$v" | cut -d. -f2)
        if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; then
            PY_BIN="$candidate"
            ok "Python: $candidate ($v)"
            break
        fi
    fi
done
[ -z "$PY_BIN" ] && die "Python 3.10+ not found. Install from https://www.python.org/downloads/"

# --- Node ----------------------------------------------------------------
if ! command -v node >/dev/null 2>&1; then
    die "Node.js not found. Install Node 18+ from https://nodejs.org"
fi
NODE_V=$(node -v | sed 's/v//')
NODE_MAJOR=$(echo "$NODE_V" | cut -d. -f1)
[ "$NODE_MAJOR" -lt 18 ] && die "Node $NODE_V is too old, need 18+."
ok "Node:   $(node -v)"

# --- Yarn ----------------------------------------------------------------
if ! command -v yarn >/dev/null 2>&1; then
    warn "Yarn not found. Enabling via Corepack…"
    if command -v corepack >/dev/null 2>&1; then
        corepack enable >/dev/null 2>&1 || true
        corepack prepare yarn@1.22.22 --activate >/dev/null 2>&1 || true
    fi
    if ! command -v yarn >/dev/null 2>&1; then
        warn "Falling back to: npm install -g yarn"
        npm install -g yarn >/dev/null 2>&1 || die "Could not install yarn. Run: npm i -g yarn"
    fi
fi
ok "Yarn:   $(yarn -v)"

# --- MongoDB -------------------------------------------------------------
MONGO_MODE=""
if command -v mongosh >/dev/null 2>&1 && mongosh --quiet --eval 'db.runCommand({ ping: 1 })' mongodb://localhost:27017 >/dev/null 2>&1; then
    MONGO_MODE="local"; ok "MongoDB: detected running on localhost:27017"
elif command -v mongo >/dev/null 2>&1 && mongo --quiet --eval 'db.runCommand({ ping: 1 })' mongodb://localhost:27017 >/dev/null 2>&1; then
    MONGO_MODE="local"; ok "MongoDB: detected running on localhost:27017 (legacy client)"
elif (echo > /dev/tcp/127.0.0.1/27017) >/dev/null 2>&1; then
    MONGO_MODE="local"; ok "MongoDB: port 27017 is open locally"
elif command -v docker >/dev/null 2>&1; then
    MONGO_MODE="docker"
    warn "MongoDB not detected locally — will use Docker container 'triageai-mongo'."
else
    die "Neither a local MongoDB on port 27017 nor Docker is available.\nInstall MongoDB (https://www.mongodb.com/try/download/community) or Docker Desktop (https://www.docker.com/products/docker-desktop)."
fi
echo "$MONGO_MODE" > "$RUN_DIR/mongo.mode"

# =============================================================================
# 2. BACKEND
# =============================================================================
echo
log "Setting up backend…"

if [ ! -d "$VENV_DIR" ]; then
    "$PY_BIN" -m venv "$VENV_DIR"
    ok "Created virtualenv at backend/.venv"
else
    ok "Reusing virtualenv at backend/.venv"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

log "Upgrading pip / wheel / setuptools…"
python -m pip install --upgrade pip wheel setuptools >> "$LOG_DIR/pip.log" 2>&1

log "Installing Python dependencies (this can take 3–5 min the first time)…"
pip install \
    --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ \
    -r "$REPO_DIR/backend/requirements.txt" >> "$LOG_DIR/pip.log" 2>&1
ok "Backend dependencies installed"

# Ensure backend/.env exists and contains local-friendly defaults
BACKEND_ENV="$REPO_DIR/backend/.env"
if [ ! -f "$BACKEND_ENV" ]; then
    log "Generating backend/.env"
    JWT_RANDOM=$(python -c 'import secrets; print(secrets.token_hex(32))')
    cat > "$BACKEND_ENV" <<EOF
MONGO_URL="mongodb://localhost:27017"
DB_NAME="triageai_local"
CORS_ORIGINS="*"
JWT_SECRET="$JWT_RANDOM"
EMERGENT_LLM_KEY=""
EOF
    ok "Wrote backend/.env (set EMERGENT_LLM_KEY there to enable AI triage)"
else
    ok "Found existing backend/.env (left untouched)"
fi

deactivate || true

# =============================================================================
# 3. FRONTEND
# =============================================================================
echo
log "Setting up frontend…"

# CRA reads .env.local with higher priority than .env — keeps the protected
# .env intact while overriding for local dev.
FRONTEND_ENV_LOCAL="$REPO_DIR/frontend/.env.local"
cat > "$FRONTEND_ENV_LOCAL" <<'EOF'
REACT_APP_BACKEND_URL=http://localhost:8001
WDS_SOCKET_PORT=3000
DANGEROUSLY_DISABLE_HOST_CHECK=true
BROWSER=none
EOF
ok "Wrote frontend/.env.local pointing at http://localhost:8001"

log "Installing frontend dependencies via yarn (this can take 2–4 min)…"
(cd "$REPO_DIR/frontend" && yarn install --network-timeout 1000000 >> "$LOG_DIR/yarn.log" 2>&1)
ok "Frontend dependencies installed"

# =============================================================================
# 4. DONE
# =============================================================================
echo
printf "${GRN}${BLD}Setup complete!${CLR}\n\n"
printf "Next steps:\n"
printf "  ${BLD}1.${CLR} (Optional) Add your Emergent LLM key in ${BLD}backend/.env${CLR} → EMERGENT_LLM_KEY=…\n"
printf "  ${BLD}2.${CLR} Start everything:  ${BLU}./local/start.sh${CLR}\n"
printf "  ${BLD}3.${CLR} Open the app:      ${BLU}http://localhost:3000${CLR}\n\n"
printf "  Stop:   ${BLU}./local/stop.sh${CLR}\n"
printf "  Reseed: ${BLU}./local/seed.sh${CLR}\n"
printf "  Reset:  ${BLU}./local/reset.sh${CLR}   (wipes Mongo data)\n\n"
printf "Demo logins (created on first backend start):\n"
printf "  • admin@triage.ai  / admin123   (admin)\n"
printf "  • sre1@triage.ai   / sre123     (on-call)\n"
printf "  • sre2@triage.ai   / sre123     (on-call)\n"
printf "  • viewer@triage.ai / viewer123  (viewer)\n\n"
