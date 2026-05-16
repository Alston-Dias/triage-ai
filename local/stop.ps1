# Stops backend, frontend (and Mongo container with --all) on Windows.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunDir = Join-Path $ScriptDir '.run'
function Ok($m)   { Write-Host "✓ $m" -ForegroundColor Green }
function Warn($m) { Write-Host "! $m" -ForegroundColor Yellow }

function Stop-PidFile($name,$file) {
    if (Test-Path $file) {
        $pidVal = (Get-Content $file -Raw).Trim()
        if ($pidVal) {
            try { Stop-Process -Id ([int]$pidVal) -Force -ErrorAction Stop; Ok "$name stopped (PID $pidVal)" }
            catch { Warn "$name had a stale PID file" }
        }
        Remove-Item $file -Force
    } else { Warn "$name is not running" }
}

Stop-PidFile 'Frontend' (Join-Path $RunDir 'frontend.pid')
Stop-PidFile 'Backend'  (Join-Path $RunDir 'backend.pid')

# free orphan ports
foreach ($p in 3000,8001) {
    try {
        $pids = (Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue).OwningProcess | Sort-Object -Unique
        foreach ($procId in $pids) { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue; Warn "Freed port $p" }
    } catch {}
}

if ($args -contains '--all') {
    $names = & docker ps --format '{{.Names}}' 2>$null
    if ($names -contains 'triageai-mongo') { & docker stop triageai-mongo | Out-Null; Ok 'MongoDB container stopped' }
}

Write-Host ''
Write-Host 'Done.' -ForegroundColor White
