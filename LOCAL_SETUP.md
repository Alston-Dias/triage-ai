# TriageAI · Local Setup

Run the entire TriageAI stack (FastAPI backend, React frontend, MongoDB) on your own machine with one command. Dummy data is seeded automatically the first time you start the stack.

## Prerequisites

You need **either** of these setups installed:

| Requirement | macOS / Linux                                     | Windows                                    |
|-------------|---------------------------------------------------|--------------------------------------------|
| **Python 3.10 – 3.13** (not 3.14) | `brew install python@3.12` / `apt install python3.12 python3.12-venv` | https://www.python.org/downloads/release/python-3127/ |
| Node 18+    | `brew install node` / NodeSource                  | https://nodejs.org                         |
| Yarn        | auto-installed via corepack                        | auto-installed via corepack                |
| MongoDB     | `brew services start mongodb-community` **or** Docker | MongoDB Community service **or** Docker Desktop |

> **Python 3.14 is too new** for the pinned scientific/grpc dependencies (scikit-learn, grpcio-status, pandas). The setup script will refuse to run on 3.14 and tell you exactly how to install 3.12. If you're on Apple Silicon with brew: `brew install python@3.12 && brew link --overwrite python@3.12`.

> If MongoDB isn't installed, the setup script will automatically use a Docker container (`mongo:7`). You'll still need Docker installed in that case.

## One-command setup

From the repo root:

```bash
# macOS / Linux / WSL
chmod +x local/*.sh
./local/setup.sh        # installs everything (3–6 min first time)
./local/start.sh        # starts MongoDB + backend + frontend + seeds dummy data
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File local\setup.ps1
powershell -ExecutionPolicy Bypass -File local\start.ps1
```

When it's done you'll see:

```
  Frontend:  http://localhost:3000
  Backend:   http://localhost:8001/api/
  MongoDB:   mongodb://localhost:27017
```

Open http://localhost:3000 and log in with any demo account:

| Email              | Password   | Role     |
|--------------------|------------|----------|
| admin@triage.ai    | admin123   | admin    |
| sre1@triage.ai     | sre123     | on-call  |
| sre2@triage.ai     | sre123     | on-call  |
| viewer@triage.ai   | viewer123  | viewer   |

## What the scripts do

| Script                    | What it does                                                              |
|---------------------------|---------------------------------------------------------------------------|
| `local/setup.sh`          | Checks prerequisites, creates `backend/.venv`, installs Python + JS deps, writes `frontend/.env.local` pointing at `http://localhost:8001`. |
| `local/start.sh`          | Brings MongoDB up (host or Docker), starts the backend, waits for it to be ready, seeds dummy data the first time, starts the frontend. PIDs live in `local/.run/`. |
| `local/seed.sh`           | Idempotent dummy-data seeder. Re-run any time. Logs in as `admin@triage.ai`. |
| `local/stop.sh`           | Stops backend + frontend. Add `--all` to also stop the Mongo container.   |
| `local/reset.sh`          | Drops the local DB (prompts first). Run `start.sh` again to reseed.       |
| `local/docker-compose.mongo.yml` | Stand-alone MongoDB compose file (used automatically when no local Mongo is detected). |

## Where things live

```
backend/.env          ← MONGO_URL, DB_NAME, JWT_SECRET, EMERGENT_LLM_KEY
frontend/.env.local   ← REACT_APP_BACKEND_URL = http://localhost:8001 (created by setup)
backend/.venv/        ← Python virtualenv
local/.run/           ← PID files, mongo.mode, seeded.flag
local/.run/logs/      ← backend.log, frontend.log, pip.log, yarn.log
```

## Enabling AI features

AI triage, predictive explanations, and the Code Quality fix suggestions use an LLM. If you have an **Emergent LLM key**, put it in `backend/.env`:

```
EMERGENT_LLM_KEY="sk-emergent-..."
```

Then restart: `./local/stop.sh && ./local/start.sh`. Without a key the UI works fully — only the LLM-powered actions will return an error.

## Common issues

- **`Python 3.14` detected / `grpcio-status` resolution-impossible error** — Python 3.14 is too new for the pinned scientific/grpc deps. Install Python 3.12: `brew install python@3.12 && brew link --overwrite python@3.12 && hash -r`, then re-run `./local/setup.sh` (it will auto-detect the new interpreter and rebuild the venv).
- **Port already in use** — `start.sh` automatically frees ports 3000 and 8001 from orphaned processes before launching. If it can't, run `./local/stop.sh` first.
- **MongoDB connection refused** — start Mongo (`brew services start mongodb-community` or `sudo systemctl start mongod`) and re-run `./local/start.sh`. To switch to the Docker fallback delete `local/.run/mongo.mode` and re-run `setup.sh`.
- **`emergentintegrations` install fails** — make sure your network can reach `https://d33sy5i8bnduwe.cloudfront.net`. The setup script passes this as an extra index URL to pip.
- **Frontend stuck on compile** — the first compile can take 60–90s on slower machines. Watch `local/.run/logs/frontend.log`.
- **Backend `joblib`/`scipy` import errors** — run `./local/setup.sh` again, it reinstalls the pinned versions of these scientific deps (used by the predictive engine).

## Going deeper

```bash
# follow logs
tail -f local/.run/logs/backend.log
tail -f local/.run/logs/frontend.log

# re-seed without restarting
./local/seed.sh

# wipe DB & start fresh
./local/stop.sh
./local/reset.sh
./local/start.sh

# completely stop (incl. Mongo container)
./local/stop.sh --all
```
