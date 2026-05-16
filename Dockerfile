# syntax=docker/dockerfile:1.6
# =============================================================================
# TriageAI · All-in-one container
# Runs MongoDB + FastAPI backend + built React frontend in a single image.
# Same data flow as the local setup: Mongo starts, backend boots, dummy data
# is seeded on first run, then the SPA + API are served on port 8001.
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1 · Build the React frontend
# -----------------------------------------------------------------------------
FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /build

# Install deps first for better layer caching
COPY frontend/package.json frontend/yarn.lock ./
RUN --mount=type=cache,target=/usr/local/share/.cache/yarn \
    yarn install --frozen-lockfile --network-timeout 1000000

# Copy source and build. We deliberately leave REACT_APP_BACKEND_URL empty so
# the built JS uses *relative* /api/... URLs and hits whatever host serves it
# — perfect for an all-in-one container behind any load balancer.
COPY frontend/ ./
ENV REACT_APP_BACKEND_URL=""
ENV GENERATE_SOURCEMAP=false
ENV DISABLE_ESLINT_PLUGIN=true
RUN yarn build


# -----------------------------------------------------------------------------
# Stage 2 · Runtime: Python + MongoDB + supervisord
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Avoid interactive tzdata, keep pip lean
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MONGO_VERSION=7.0

# --- System packages ---------------------------------------------------------
# Includes MongoDB 7 (official repo), supervisord, curl/jq for the seeder,
# gosu for safe privilege drop.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg jq tini supervisor procps gosu \
        build-essential ; \
    install -d -m 0755 /etc/apt/keyrings; \
    curl -fsSL https://www.mongodb.org/static/pgp/server-${MONGO_VERSION}.asc \
        | gpg --dearmor -o /etc/apt/keyrings/mongodb-server-${MONGO_VERSION}.gpg; \
    echo "deb [ signed-by=/etc/apt/keyrings/mongodb-server-${MONGO_VERSION}.gpg ] https://repo.mongodb.org/apt/debian bookworm/mongodb-org/${MONGO_VERSION} main" \
        > /etc/apt/sources.list.d/mongodb-org-${MONGO_VERSION}.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends mongodb-org; \
    apt-get purge -y --auto-remove build-essential; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# --- Python deps -------------------------------------------------------------
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip wheel setuptools && \
    pip install \
        --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ \
        -r /app/backend/requirements.txt

# --- App code ---------------------------------------------------------------
COPY backend/ /app/backend/
# Copy the built React app to a stable location that server.py looks at
COPY --from=frontend-builder /build/build /app/frontend_build

# Supervisord + boot scripts
COPY docker/supervisord.conf /etc/supervisor/conf.d/triageai.conf
COPY docker/entrypoint.sh    /usr/local/bin/entrypoint.sh
COPY docker/seed.sh          /usr/local/bin/seed.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/seed.sh && \
    mkdir -p /data/db /var/log/supervisor /var/log/mongo && \
    chown -R mongodb:mongodb /data/db /var/log/mongo

# --- Default env -------------------------------------------------------------
ENV MONGO_URL="mongodb://127.0.0.1:27017" \
    DB_NAME="triageai" \
    CORS_ORIGINS="*" \
    LLM_PROVIDER="emergent" \
    EMERGENT_LLM_KEY="" \
    LLM_BASE_URL="" \
    LLM_API_KEY="" \
    LLM_MODEL="" \
    PORT="8001"

EXPOSE 8001
VOLUME ["/data/db"]

# Tini reaps zombies; supervisord runs the multi-process container.
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]

HEALTHCHECK --interval=20s --timeout=5s --start-period=60s --retries=4 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/" >/dev/null || exit 1
