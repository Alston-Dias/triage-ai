#!/usr/bin/env bash
# Entrypoint for the all-in-one TriageAI container.
# - Initialises /data/db (Mongo data dir)
# - Materialises two .env files from runtime env vars so server.py's
#   load_dotenv() picks them up:
#       /app/backend/.env  → infrastructure (MONGO_URL, DB_NAME, JWT_SECRET, ...)
#       /app/.env          → LLM gateway config (MODEL, GATEWAY_*, ...)
# - Hands off to supervisord (passed as CMD)
set -Eeuo pipefail

# --- Make sure mongo data dir exists & is owned by mongodb ------------------
mkdir -p /data/db /var/log/mongo /var/log/supervisor
chown -R mongodb:mongodb /data/db /var/log/mongo 2>/dev/null || true

# --- Defaults --------------------------------------------------------------
: "${MONGO_URL:=mongodb://127.0.0.1:27017}"
: "${DB_NAME:=triageai}"
: "${CORS_ORIGINS:=*}"
: "${LLM_PROVIDER:=gateway}"
: "${MODEL:=gpt-5.2-CIO}"
: "${GATEWAY_BASE_URL:=https://hub-proxy-service.thankfulfield-16b4d5d6.eastus.azurecontainerapps.io/v1}"
: "${GATEWAY_API_KEY:=}"
: "${EMBEDDINGS_MODEL:=embeddings}"
: "${LLM_TIMEOUT_SECONDS:=90}"
: "${EMERGENT_LLM_KEY:=}"
: "${JWT_SECRET:=}"

# Generate a random JWT secret on first boot if the operator didn't supply one
if [ -z "${JWT_SECRET:-}" ]; then
    JWT_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))')
fi

# --- backend/.env : infrastructure + legacy keys ----------------------------
BACKEND_ENV=/app/backend/.env
cat > "$BACKEND_ENV" <<EOF
MONGO_URL="${MONGO_URL}"
DB_NAME="${DB_NAME}"
CORS_ORIGINS="${CORS_ORIGINS}"
JWT_SECRET="${JWT_SECRET}"
EMERGENT_LLM_KEY="${EMERGENT_LLM_KEY}"
EOF

# --- /app/.env : LLM gateway --------------------------------------------------
ROOT_ENV=/app/.env
cat > "$ROOT_ENV" <<EOF
LLM_PROVIDER="${LLM_PROVIDER}"
MODEL="${MODEL}"
GATEWAY_BASE_URL="${GATEWAY_BASE_URL}"
GATEWAY_API_KEY="${GATEWAY_API_KEY}"
EMBEDDINGS_MODEL="${EMBEDDINGS_MODEL}"
LLM_TIMEOUT_SECONDS="${LLM_TIMEOUT_SECONDS}"
EOF

if [ -z "${GATEWAY_API_KEY}" ] && [ -z "${EMERGENT_LLM_KEY}" ]; then
    echo "[entrypoint] WARNING: neither GATEWAY_API_KEY nor EMERGENT_LLM_KEY is set."
    echo "[entrypoint] AI features (triage, chat, code analysis) will fall back to canned responses."
fi

echo "[entrypoint] data dir ready, env materialised (model=${MODEL}), handing off to supervisord…"
exec "$@"
