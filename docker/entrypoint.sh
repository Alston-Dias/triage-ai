#!/usr/bin/env bash
# Entrypoint for the all-in-one TriageAI container.
# - Initialises /data/db (Mongo data dir)
# - Writes a /app/backend/.env from runtime env vars (so server.py's load_dotenv
#   sees them) if one isn't already baked in
# - Hands off to supervisord (passed as CMD)
set -Eeuo pipefail

# --- Make sure mongo data dir exists & is owned by mongodb ------------------
mkdir -p /data/db /var/log/mongo /var/log/supervisor
chown -R mongodb:mongodb /data/db /var/log/mongo 2>/dev/null || true

# --- Materialise an .env that backend/server.py will load -------------------
# server.py uses python-dotenv at import time. We project the *current* env
# into backend/.env so changes via `docker run -e ...` actually take effect
# even if a stale .env was baked into the image.
ENV_FILE=/app/backend/.env
: "${MONGO_URL:=mongodb://127.0.0.1:27017}"
: "${DB_NAME:=triageai}"
: "${CORS_ORIGINS:=*}"
: "${LLM_PROVIDER:=emergent}"
: "${EMERGENT_LLM_KEY:=}"
: "${LLM_BASE_URL:=}"
: "${LLM_API_KEY:=}"
: "${LLM_MODEL:=}"
: "${LLM_TIMEOUT_SECONDS:=90}"
: "${JWT_SECRET:=}"

# Generate a random JWT secret on first boot if the operator didn't supply one
if [ -z "${JWT_SECRET:-}" ]; then
    JWT_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))')
fi

cat > "$ENV_FILE" <<EOF
MONGO_URL="${MONGO_URL}"
DB_NAME="${DB_NAME}"
CORS_ORIGINS="${CORS_ORIGINS}"
LLM_PROVIDER="${LLM_PROVIDER}"
EMERGENT_LLM_KEY="${EMERGENT_LLM_KEY}"
LLM_BASE_URL="${LLM_BASE_URL}"
LLM_API_KEY="${LLM_API_KEY}"
LLM_MODEL="${LLM_MODEL}"
LLM_TIMEOUT_SECONDS="${LLM_TIMEOUT_SECONDS}"
JWT_SECRET="${JWT_SECRET}"
EOF

echo "[entrypoint] data dir ready, env materialised, handing off to supervisord…"
exec "$@"
