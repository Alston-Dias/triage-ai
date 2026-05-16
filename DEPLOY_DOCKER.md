# TriageAI · Docker / AWS Deployment

The root `Dockerfile` produces a **single all-in-one image** that contains:

- The FastAPI backend (port 8001)
- The built React frontend, served by the same FastAPI process on `/`
- A MongoDB 7 server running inside the container (`/data/db`)
- A first-boot dummy-data seeder (same flow as the local `seed.sh`)

It's the same shape as the local setup, just bundled into one container so it
drops cleanly into AWS App Runner, ECS Fargate, EC2 (Docker), Lightsail
Containers, or Elastic Beanstalk (Docker platform).

## Build it

From the repo root:

```bash
docker build -t triageai:latest .
```

First build takes ~5–7 min (frontend + Python deps + MongoDB apt repo).
Subsequent rebuilds are cached and fast.

## Run it locally to test

```bash
docker run -d --name triageai \
    -p 8001:8001 \
    -v triageai-data:/data/db \
    triageai:latest

# follow logs
docker logs -f triageai
```

Open http://localhost:8001 and log in with `sre1@triage.ai` / `sre123`.
(The seeder runs once on first boot, the flag is kept in the `/data/db`
volume so restarts skip it.)

Stop & restart:

```bash
docker stop triageai && docker start triageai
```

Reset everything (drops the DB):

```bash
docker rm -f triageai
docker volume rm triageai-data
```

## Environment variables (all optional)

| Variable                     | Default                              | What it does                                                                                                  |
|------------------------------|--------------------------------------|---------------------------------------------------------------------------------------------------------------|
| `PORT`                       | `8001`                               | HTTP port the container listens on                                                                            |
| `MONGO_URL`                  | `mongodb://127.0.0.1:27017`          | Override if you point at AWS DocumentDB / Atlas instead of the bundled mongod                                 |
| `DB_NAME`                    | `triageai`                           | Mongo database name                                                                                           |
| `JWT_SECRET`                 | random per first-boot                | Set this in prod so user tokens survive restarts                                                              |
| `CORS_ORIGINS`               | `*`                                  | Comma-separated list of allowed origins                                                                       |
| **LLM configuration**        |                                      |                                                                                                               |
| `LLM_PROVIDER`               | `emergent`                           | `emergent` (default, uses Emergent LLM key) **or** `openai`/`openai_compatible`/`ibm_bob` to use a custom URL |
| `EMERGENT_LLM_KEY`           | empty                                | Required when `LLM_PROVIDER=emergent`                                                                         |
| `LLM_BASE_URL`               | empty                                | OpenAI-compatible endpoint (e.g. `https://your-bob.ibm.com/v1`)                                               |
| `LLM_API_KEY`                | empty                                | Bearer token / API key for the custom provider                                                                |
| `LLM_MODEL`                  | empty                                | Model name (e.g. `ibm/granite-3-8b-instruct`, `gpt-4o-mini`)                                                  |
| `LLM_TIMEOUT_SECONDS`        | `90`                                 | Per-call timeout                                                                                              |
| `LLM_EXTRA_HEADER_*`         | none                                 | Any env var of the form `LLM_EXTRA_HEADER_X_Project_Id=abc123` is sent as an HTTP header (`X-Project-Id`)     |

### Switching to IBM "Bob" / any custom LLM

When you get your IBM Bob key, just run with:

```bash
docker run -d --name triageai \
    -p 8001:8001 \
    -v triageai-data:/data/db \
    -e LLM_PROVIDER=openai \
    -e LLM_BASE_URL="https://bob.your-ibm-endpoint.com/v1" \
    -e LLM_API_KEY="YOUR-BOB-KEY" \
    -e LLM_MODEL="ibm/granite-3-8b-instruct" \
    triageai:latest
```

No code changes needed — the backend will route every AI call (incident triage,
incident chat, predictive remediation, code-quality fixes) through the custom
endpoint. If your Bob API needs extra headers (project id, tenant, etc.):

```bash
    -e LLM_EXTRA_HEADER_X_Project_Id="abcd-1234"
```

## Using AWS DocumentDB or MongoDB Atlas instead of the bundled mongod

Simply point `MONGO_URL` at the external cluster — the in-container mongod is
still running but is ignored. To strip it out for a leaner image, comment out
the `[program:mongod]` section of `docker/supervisord.conf` and rebuild.

```bash
docker run -d --name triageai \
    -p 8001:8001 \
    -e MONGO_URL="mongodb+srv://user:pass@your-cluster.xxx.mongodb.net/?retryWrites=true&w=majority" \
    -e DB_NAME=triageai \
    triageai:latest
```

## Pushing to AWS

```bash
# 1. Create an ECR repository (once)
aws ecr create-repository --repository-name triageai

# 2. Authenticate Docker to ECR
AWS_ACCT=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${AWS_REGION:-us-east-1}
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $AWS_ACCT.dkr.ecr.$AWS_REGION.amazonaws.com

# 3. Tag + push
docker tag triageai:latest $AWS_ACCT.dkr.ecr.$AWS_REGION.amazonaws.com/triageai:latest
docker push $AWS_ACCT.dkr.ecr.$AWS_REGION.amazonaws.com/triageai:latest
```

From there:

- **App Runner**  → Create service → select the ECR image → port 8001 → add env vars → deploy.
- **ECS Fargate** → Task definition with one container, port 8001, an attached EFS or EBS volume mounted at `/data/db` if you want Mongo data to persist, ALB target group on 8001.
- **EC2 (single host)** → SSH in, `docker run -d -p 80:8001 ...`.

> Persistence: AWS App Runner doesn't support persistent volumes. If you use
> App Runner, **always** point `MONGO_URL` at Atlas or DocumentDB — the
> in-container Mongo will lose all data on every redeploy.

## Demo logins (created on first boot)

| Email              | Password   | Role     |
|--------------------|------------|----------|
| admin@triage.ai    | admin123   | admin    |
| sre1@triage.ai     | sre123     | on-call  |
| sre2@triage.ai     | sre123     | on-call  |
| viewer@triage.ai   | viewer123  | viewer   |

## Troubleshooting

```bash
docker exec -it triageai bash                 # shell into the container
tail -f /var/log/supervisor/backend.err.log   # backend logs
tail -f /var/log/supervisor/mongod.out.log    # mongo logs
tail -f /var/log/supervisor/seeder.out.log    # first-boot seed output
```

Force re-seed (e.g. after wiping the DB):

```bash
docker exec triageai rm /data/db/.seeded
docker exec triageai /usr/local/bin/seed.sh
```
