# Starts MongoDB (docker if needed), backend, frontend on Windows.
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

if (-not (Test-Path $VenvDir)) { Die 'Backend venv missing — run local\setup.ps1 first.' }
if (-not (Test-Path (Join-Path $RepoDir 'frontend\node_modules'))) { Die 'Frontend deps missing — run local\setup.ps1 first.' }

$MongoMode = 'local'
$mmFile = Join-Path $RunDir 'mongo.mode'
if (Test-Path $mmFile) { $MongoMode = (Get-Content $mmFile -Raw).Trim() }

function Test-Port($p) {
    try { return (New-Object System.Net.Sockets.TcpClient).ConnectAsync('127.0.0.1',$p).Wait(600) } catch { return $false }
}

function Free-Port($p) {
    try {
        $pids = (Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue).OwningProcess | Sort-Object -Unique
        foreach ($procId in $pids) { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue }
    } catch {}
}

function Is-Alive($pidFile) {
    if (-not (Test-Path $pidFile)) { return $false }
    $pidVal = Get-Content $pidFile -Raw
    if (-not $pidVal) { return $false }
    $pidInt = [int]($pidVal.Trim())
    return (Get-Process -Id $pidInt -ErrorAction SilentlyContinue) -ne $null
}

Write-Host ''
Write-Host 'Starting TriageAI locally…' -ForegroundColor White
Write-Host ''

# Mongo
if ($MongoMode -eq 'docker') {
    $names = & docker ps --format '{{.Names}}'
    if ($names -contains 'triageai-mongo') {
        Ok 'MongoDB container already running'
    } else {
        $all = & docker ps -a --format '{{.Names}}'
        if ($all -contains 'triageai-mongo') {
            Log 'Starting existing MongoDB container…'
            & docker start triageai-mongo | Out-Null
        } else {
            Log 'Creating MongoDB container triageai-mongo on port 27017…'
            & docker run -d --name triageai-mongo -p 27017:27017 -v triageai-mongo-data:/data/db --restart unless-stopped mongo:7 | Out-Null
        }
        for ($i = 0; $i -lt 30; $i++) {
            if (Test-Port 27017) { Ok 'MongoDB ready'; break }
            Start-Sleep -Seconds 1
            if ($i -eq 29) { Die 'MongoDB never came up.' }
        }
    }
} else {
    if (-not (Test-Port 27017)) { Die 'MongoDB is not running on localhost:27017. Start it from Services, or rerun setup to switch to Docker.' }
    Ok 'MongoDB reachable on localhost:27017'
}

$BackendPidFile  = Join-Path $RunDir 'backend.pid'
$FrontendPidFile = Join-Path $RunDir 'frontend.pid'

if (Is-Alive $BackendPidFile) {
    Ok "Backend already running (PID $(Get-Content $BackendPidFile))"
} else {
    Free-Port 8001
    Log 'Starting backend (uvicorn) on http://localhost:8001'
    $Activate = Join-Path $VenvDir 'Scripts\python.exe'
    $args = '-m uvicorn server:app --host 0.0.0.0 --port 8001 --reload'
    $proc = Start-Process -FilePath $Activate -ArgumentList $args -WorkingDirectory (Join-Path $RepoDir 'backend') -RedirectStandardOutput (Join-Path $LogDir 'backend.log') -RedirectStandardError (Join-Path $LogDir 'backend.err.log') -PassThru -WindowStyle Hidden
    Set-Content -Path $BackendPidFile -Value $proc.Id
    for ($i = 0; $i -lt 40; $i++) {
        try { Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8001/api/' -TimeoutSec 2 | Out-Null; Ok 'Backend up'; break } catch { Start-Sleep -Seconds 1 }
        if ($i -eq 39) { Warn 'Backend did not respond in 40s — see backend.log'; }
    }
}

$seededFlag = Join-Path $RunDir 'seeded.flag'
if (-not (Test-Path $seededFlag)) {
    Log 'Seeding dummy data…'
    try {
        $login = Invoke-RestMethod -Method Post -Uri 'http://localhost:8001/api/auth/login' -ContentType 'application/json' -Body (@{email='admin@triage.ai'; password='admin123'} | ConvertTo-Json)
        $headers = @{ Authorization = "Bearer $($login.access_token)" }
        Invoke-RestMethod -Method Post -Uri 'http://localhost:8001/api/seed' -Headers $headers | Out-Null
        Invoke-RestMethod -Method Post -Uri 'http://localhost:8001/api/demo/age-alerts' -Headers $headers | Out-Null
        for ($i=0; $i -lt 4; $i++) { try { Invoke-RestMethod -Method Post -Uri 'http://localhost:8001/api/alerts/simulate' -Headers $headers | Out-Null } catch {} }
        New-Item -ItemType File -Force -Path $seededFlag | Out-Null
        Ok 'Dummy data seeded'
    } catch { Warn "Seeding failed: $($_.Exception.Message)" }
} else {
    Ok 'Dummy data already seeded'
}

if (Is-Alive $FrontendPidFile) {
    Ok "Frontend already running (PID $(Get-Content $FrontendPidFile))"
} else {
    Free-Port 3000
    Log 'Starting frontend (CRA) on http://localhost:3000'
    $proc = Start-Process -FilePath 'yarn' -ArgumentList 'start' -WorkingDirectory (Join-Path $RepoDir 'frontend') -RedirectStandardOutput (Join-Path $LogDir 'frontend.log') -RedirectStandardError (Join-Path $LogDir 'frontend.err.log') -PassThru -WindowStyle Hidden
    Set-Content -Path $FrontendPidFile -Value $proc.Id
    for ($i = 0; $i -lt 90; $i++) {
        try { Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:3000' -TimeoutSec 2 | Out-Null; Ok 'Frontend up'; break } catch { Start-Sleep -Seconds 1 }
        if ($i -eq 89) { Warn 'Frontend still compiling — open http://localhost:3000 in a minute.' }
    }
}

Write-Host ''
Write-Host 'All services running.' -ForegroundColor Green
Write-Host ''
Write-Host '  Frontend:  http://localhost:3000'
Write-Host '  Backend:   http://localhost:8001/api/'
Write-Host '  MongoDB:   mongodb://localhost:27017'
Write-Host ''
Write-Host '  Demo login: sre1@triage.ai / sre123'
Write-Host '  Stop:       powershell -ExecutionPolicy Bypass -File local\stop.ps1'
Write-Host ''
