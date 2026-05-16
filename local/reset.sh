#!/usr/bin/env bash
# Wipes the local database (DB_NAME from backend/.env) so a fresh seed can run.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_DIR="$SCRIPT_DIR/.run"

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'; BLD='\033[1m'; CLR='\033[0m'

# Read DB_NAME from backend/.env (default to triageai_local)
DB_NAME="triageai_local"
if [ -f "$REPO_DIR/backend/.env" ]; then
    val=$(grep -E '^DB_NAME=' "$REPO_DIR/backend/.env" | tail -n1 | cut -d= -f2 | tr -d '"' | tr -d "'")
    [ -n "$val" ] && DB_NAME="$val"
fi

printf "${YLW}${BLD}This will drop database '${DB_NAME}' from mongodb://localhost:27017.${CLR}\n"
read -r -p "Continue? [y/N] " ans
[ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "Aborted."; exit 0; }

DROP_JS="db.getSiblingDB('$DB_NAME').dropDatabase()"
if command -v mongosh >/dev/null 2>&1; then
    mongosh --quiet --eval "$DROP_JS" mongodb://localhost:27017 >/dev/null
elif command -v mongo >/dev/null 2>&1; then
    mongo --quiet --eval "$DROP_JS" mongodb://localhost:27017 >/dev/null
elif command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -q '^triageai-mongo$'; then
    docker exec triageai-mongo mongosh --quiet --eval "$DROP_JS" >/dev/null
else
    printf "${RED}No mongo client (mongosh/mongo/docker) available to drop the DB.${CLR}\n" >&2
    exit 1
fi

rm -f "$RUN_DIR/seeded.flag"
printf "${GRN}✓ Database '$DB_NAME' dropped.${CLR}  Re-run ./local/start.sh to recreate & re-seed.\n"
