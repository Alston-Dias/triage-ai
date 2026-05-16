#!/usr/bin/env bash
# Stops backend, frontend and (optionally) the Mongo docker container.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$SCRIPT_DIR/.run"

GRN='\033[0;32m'; YLW='\033[0;33m'; BLD='\033[1m'; CLR='\033[0m'
ok()   { printf "${GRN}✓${CLR} %s\n" "$*"; }
warn() { printf "${YLW}!${CLR} %s\n" "$*"; }

stop_pidfile() {
    local name=$1 file=$2
    if [ -f "$file" ]; then
        local pid; pid=$(cat "$file")
        if kill -0 "$pid" 2>/dev/null; then
            # Kill the whole process group so child npm/node procs die too.
            kill -TERM -- -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
            sleep 1
            kill -KILL -- -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
            ok "$name stopped (PID $pid)"
        else
            warn "$name had a stale PID file"
        fi
        rm -f "$file"
    else
        warn "$name is not running"
    fi
}

stop_pidfile "Frontend" "$RUN_DIR/frontend.pid"
stop_pidfile "Backend"  "$RUN_DIR/backend.pid"

# Free residual children just in case
if command -v lsof >/dev/null 2>&1; then
    for port in 3000 8001; do
        pids=$(lsof -t -i ":$port" 2>/dev/null || true)
        [ -n "$pids" ] && { kill $pids 2>/dev/null || true; sleep 0.5; kill -9 $pids 2>/dev/null || true; warn "Freed port $port"; }
    done
fi

if [ "${1:-}" = "--all" ]; then
    if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -q '^triageai-mongo$'; then
        docker stop triageai-mongo >/dev/null && ok "MongoDB container stopped"
    fi
fi

printf "\n${BLD}Done.${CLR}  (Use './local/stop.sh --all' to also stop the Mongo container)\n\n"
