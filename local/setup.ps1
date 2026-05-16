# =============================================================================
# TriageAI · Local Setup (Windows / PowerShell)
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File local\setup.ps1
# =============================================================================
$ErrorActionPreference = 'Stop'

function Log($m)  { Write-Host "» $m" -ForegroundColor Blue }
function Ok($m)   { Write-Host "✓ $m" -ForegroundColor Green }
function Warn($m) { Write-Host "! $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "✗ $m" -ForegroundColor Red; exit 1 }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir   = Resolve-Path (Join-Path $ScriptDir '..')
$RunDir    = Join-Path $ScriptDir '.run'
$LogDir    = Join-Path $RunDir 'logs'
$VenvDir   = Join-Path $RepoDir 'backend\.venv'
New-Item -ItemType Directory -Force -Path $RunDir,$LogDir | Out-Null

Write-Host ""
Write-Host "╭───────────────────────────────────────────────╮" -ForegroundColor White
Write-Host "│  TriageAI · Local Setup (Windows)              │" -ForegroundColor White
Write-Host "╰───────────────────────────────────────────────╯" -ForegroundColor White
Write-Host ""

# 1. Prereqs ---------------------------------------------------------------
Log 'Checking prerequisites…'

$Py = $null
foreach ($c in @('python3.11','python3.12','python3.10','python','python3')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) {
        $v = & $c -c 'import sys; print("%d.%d" % sys.version_info[:2])'
        $major,$minor = $v.Split('.') | ForEach-Object { [int]$_ }
        if ($major -eq 3 -and $minor -ge 10) { $Py = $c; Ok "Python: $c ($v)"; break }
    }
}
if (-not $Py) { Die 'Python 3.10+ not found. Install from https://www.python.org/downloads/' }

$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) { Die 'Node.js not found. Install Node 18+ from https://nodejs.org' }
$nodeV = (& node -v).TrimStart('v'); $nodeMajor = [int]($nodeV.Split('.')[0])
if ($nodeMajor -lt 18) { Die "Node $nodeV is too old, need 18+." }
Ok "Node:   v$nodeV"

$yarnCmd = Get-Command yarn -ErrorAction SilentlyContinue
if (-not $yarnCmd) {
    Warn 'Yarn not found — enabling via corepack…'
    & corepack enable 2>$null
    & corepack prepare yarn@1.22.22 --activate 2>$null
    $yarnCmd = Get-Command yarn -ErrorAction SilentlyContinue
    if (-not $yarnCmd) {
        Warn 'Falling back to: npm install -g yarn'
        & npm install -g yarn | Out-Null
    }
}
Ok "Yarn:   $(& yarn -v)"

# MongoDB ---
$MongoMode = ''
$portOpen = $false
try { $portOpen = (New-Object System.Net.Sockets.TcpClient).ConnectAsync('127.0.0.1',27017).Wait(800) } catch {}
if ($portOpen) {
    $MongoMode = 'local'; Ok 'MongoDB: port 27017 is open locally'
} elseif (Get-Command docker -ErrorAction SilentlyContinue) {
    $MongoMode = 'docker'; Warn 'MongoDB not detected — will use Docker container triageai-mongo'
} else {
    Die 'Neither MongoDB on port 27017 nor Docker is available. Install MongoDB Community or Docker Desktop.'
}
Set-Content -Path (Join-Path $RunDir 'mongo.mode') -Value $MongoMode

# 2. Backend ---------------------------------------------------------------
Write-Host ''
Log 'Setting up backend…'
if (-not (Test-Path $VenvDir)) {
    & $Py -m venv $VenvDir
    Ok 'Created virtualenv at backend\.venv'
} else { Ok 'Reusing virtualenv at backend\.venv' }

$Pip = Join-Path $VenvDir 'Scripts\pip.exe'
$PyVenv = Join-Path $VenvDir 'Scripts\python.exe'

Log 'Upgrading pip / wheel / setuptools…'
& $PyVenv -m pip install --upgrade pip wheel setuptools *>> (Join-Path $LogDir 'pip.log')

Log 'Installing Python dependencies (3–5 min first time)…'
& $Pip install --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ -r (Join-Path $RepoDir 'backend\requirements.txt') *>> (Join-Path $LogDir 'pip.log')
Ok 'Backend dependencies installed'

$BackendEnv = Join-Path $RepoDir 'backend\.env'
if (-not (Test-Path $BackendEnv)) {
    $jwt = & $PyVenv -c 'import secrets; print(secrets.token_hex(32))'
    @"
MONGO_URL="mongodb://localhost:27017"
DB_NAME="triageai_local"
CORS_ORIGINS="*"
JWT_SECRET="$jwt"
EMERGENT_LLM_KEY=""
"@ | Set-Content -Path $BackendEnv -NoNewline
    Ok 'Wrote backend\.env'
} else { Ok 'Found existing backend\.env (left untouched)' }

# 3. Frontend --------------------------------------------------------------
Write-Host ''
Log 'Setting up frontend…'
@"
REACT_APP_BACKEND_URL=http://localhost:8001
WDS_SOCKET_PORT=3000
DANGEROUSLY_DISABLE_HOST_CHECK=true
BROWSER=none
"@ | Set-Content -Path (Join-Path $RepoDir 'frontend\.env.local') -NoNewline
Ok 'Wrote frontend\.env.local pointing at http://localhost:8001'

Log 'Installing frontend dependencies (2–4 min)…'
Push-Location (Join-Path $RepoDir 'frontend')
& yarn install --network-timeout 1000000 *>> (Join-Path $LogDir 'yarn.log')
Pop-Location
Ok 'Frontend dependencies installed'

Write-Host ''
Write-Host 'Setup complete!' -ForegroundColor Green
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. (Optional) Add Emergent LLM key in backend\.env (EMERGENT_LLM_KEY=...)'
Write-Host '  2. Start everything:  powershell -ExecutionPolicy Bypass -File local\start.ps1'
Write-Host '  3. Open the app:      http://localhost:3000'
Write-Host ''
Write-Host 'Demo logins:'
Write-Host '  admin@triage.ai  / admin123'
Write-Host '  sre1@triage.ai   / sre123'
Write-Host '  sre2@triage.ai   / sre123'
Write-Host '  viewer@triage.ai / viewer123'
Write-Host ''
