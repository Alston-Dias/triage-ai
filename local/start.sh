#!/usr/bin/env bash
# Starts MongoDB (docker, if needed), backend (uvicorn) and frontend (CRA).
# All processes run in the background with PID files in local/.run
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_DIR="$SCRIPT_DIR/.run"
LOG_DIR="$RUN_DIR/logs"
VENV_DIR="$REPO_DIR/backend/.venv"

mkdir -p "$RUN_DIR" "$LOG_DIR"

GRN='\033[0;32m'; BLU='\033[0;34m'; YLW='\033[0;33m'; RED='\033[0;31m'; BLD='\033[1m'; CLR='\033[0m'
log()  { printf "${BLU}${BLD}»${CLR} %s\n" "$*"; }
ok()   { printf "${GRN}✓${CLR} %s\n" "$*"; }
warn() { printf "${YLW}!${CLR} %s\n" "$*"; }
die()  { printf "${RED}✗${CLR} %s\n" "$*" >&2; exit 1; }

[ ! -d "$VENV_DIR" ] && die "Backend venv missing — run ./local/setup.sh first."
[ ! -d "$REPO_DIR/frontend/node_modules" ] && die "Frontend deps missing — run ./local/setup.sh first."

MONGO_MODE="local"
[ -f "$RUN_DIR/mongo.mode" ] && MONGO_MODE=$(cat "$RUN_DIR/mongo.mode")

# Helper: kill anything still on our ports (orphans from a previous crash)
free_port() {
    local port=$1
    if command -v lsof >/dev/null 2>&1; then
        local pids
        pids=$(lsof -t -i ":$port" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            warn "Port $port is busy — releasing PID(s): $pids"
            kill $pids 2>/dev/null || true
            sleep 1
            kill -9 $pids 2>/dev/null || true
        fi
    fi
}

is_alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

echo
printf "${BLD}Starting TriageAI locally…${CLR}\n\n"

# ---- MongoDB ------------------------------------------------------------
if [ "$MONGO_MODE" = "docker" ]; then
    if ! command -v docker >/dev/null 2>&1; then
        die "Docker not available but mongo.mode=docker. Reinstall MongoDB or install Docker."
    fi
    if docker ps --format '{{.Names}}' | grep -q '^triageai-mongo$'; then
        ok "MongoDB container already running"
    else
        if docker ps -a --format '{{.Names}}' | grep -q '^triageai-mongo$'; then
            log "Starting existing MongoDB container…"
            docker start triageai-mongo >/dev/null
        else
            log "Creating MongoDB container 'triageai-mongo' on port 27017…"
            docker run -d --name triageai-mongo -p 27017:27017 \
                -v triageai-mongo-data:/data/db \
                --restart unless-stopped \
                mongo:7 >/dev/null
        fi
        # Wait for it
        for i in $(seq 1 30); do
            if (echo > /dev/tcp/127.0.0.1/27017) >/dev/null 2>&1; then ok "MongoDB is ready"; break; fi
            sleep 1
            [ "$i" = 30 ] && die "MongoDB never came up. Logs: docker logs triageai-mongo"
        done
    fi
else
    if ! (echo > /dev/tcp/127.0.0.1/27017) >/dev/null 2>&1; then
        die "MongoDB is not running on localhost:27017. Start it with 'brew services start mongodb-community' or 'sudo systemctl start mongod' (or rerun setup to switch to Docker)."
    fi
    ok "MongoDB reachable on localhost:27017"
fi

# ---- Backend ------------------------------------------------------------
if is_alive "$RUN_DIR/backend.pid"; then
    ok "Backend already running (PID $(cat "$RUN_DIR/backend.pid"))"
else
    free_port 8001
    log "Starting backend (uvicorn) on http://localhost:8001"
    (
        cd "$REPO_DIR/backend"
        # shellcheck disable=SC1090
        source "$VENV_DIR/bin/activate"
        nohup python -m uvicorn server:app --host 0.0.0.0 --port 8001 --reload \
            >> "$LOG_DIR/backend.log" 2>&1 &
        echo $! > "$RUN_DIR/backend.pid"
    )
    # Wait for /api/ to respond
    for i in $(seq 1 40); do
        if curl -fsS http://localhost:8001/api/ >/dev/null 2>&1; then
            ok "Backend is up"
            break
        fi
        sleep 1
        if [ "$i" = 40 ]; then
            warn "Backend didn't respond in 40s. Tail of log:"
            tail -n 30 "$LOG_DIR/backend.log" || true
            die "Backend failed to start."
        fi
    done
fi

# ---- Seed dummy data (idempotent) --------------------------------------
if [ ! -f "$RUN_DIR/seeded.flag" ]; then
    log "Seeding dummy data…"
    bash "$SCRIPT_DIR/seed.sh" || warn "Seeding failed — you can retry with ./local/seed.sh"
    touch "$RUN_DIR/seeded.flag"
else
    ok "Dummy data already seeded (./local/seed.sh to re-seed)"
fi

# ---- Frontend -----------------------------------------------------------
if is_alive "$RUN_DIR/frontend.pid"; then
    ok "Frontend already running (PID $(cat "$RUN_DIR/frontend.pid"))"
else
    free_port 3000
    log "Starting frontend (CRA) on http://localhost:3000"
    (
        cd "$REPO_DIR/frontend"
        nohup yarn start >> "$LOG_DIR/frontend.log" 2>&1 &
        echo $! > "$RUN_DIR/frontend.pid"
    )
    # Wait for frontend to compile
    for i in $(seq 1 90); do
        if curl -fsS http://localhost:3000 >/dev/null 2>&1; then
            ok "Frontend is up"
            break
        fi
        sleep 1
        if [ "$i" = 90 ]; then
            warn "Frontend didn't respond in 90s — it may still be compiling. Check $LOG_DIR/frontend.log"
            break
        fi
    done
fi

echo
printf "${GRN}${BLD}All services running.${CLR}\n\n"
printf "  Frontend:  ${BLU}http://localhost:3000${CLR}\n"
printf "  Backend:   ${BLU}http://localhost:8001/api/${CLR}\n"
printf "  MongoDB:   ${BLU}mongodb://localhost:27017${CLR}\n\n"
printf "  Demo login: ${BLD}sre1@triage.ai${CLR} / ${BLD}sre123${CLR}\n"
printf "  Logs:       ${BLU}tail -f local/.run/logs/{backend,frontend}.log${CLR}\n"
printf "  Stop:       ${BLU}./local/stop.sh${CLR}\n\n"
