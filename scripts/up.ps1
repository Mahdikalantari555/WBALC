# Run the whole stack natively on Windows (PowerShell port of scripts/up.sh).
#   .\scripts\up.ps1 up                engine :8000 + SvelteKit workspace :3000
#   .\scripts\up.ps1 up --dev          vite dev server instead of production build
#   .\scripts\up.ps1 status            what is running
#   .\scripts\up.ps1 down              stop everything
#   .\scripts\up.ps1 logs [name]       tail a log

$ErrorActionPreference = "Continue"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RunDir = Join-Path $Root ".run"
$LogDir = Join-Path $RunDir "logs"

$ApiPort = if ($env:API_PORT) { $env:API_PORT } else { "8000" }
$FrontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "3000" }
$FrontendDir = Join-Path $Root "frontend"
$EngineHealth = "http://localhost:$ApiPort/health"
$FrontendHealth = "http://localhost:$FrontendPort/api/health"
$Python = if ($env:WBALC_PYTHON) { $env:WBALC_PYTHON } else { Join-Path $Root ".venv\Scripts\python.exe" }

function Say($m) { Write-Host $m }
function Ok($m) { Write-Host "[OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Die($m) { Write-Host "[X] $m" -ForegroundColor Red; exit 1 }

# ---- arg parsing ----
$Command = "up"
$Frontend = 1
$DevMode = 0
$Rebuild = 0
$LogsName = "engine"
$i = 0
while ($i -lt $args.Count) {
    $a = $args[$i]
    switch ($a) {
        "up" { $Command = "up" }
        "down" { $Command = "down" }
        "status" { $Command = "status" }
        "logs" { $Command = "logs"; if ($i + 1 -lt $args.Count) { $LogsName = $args[$i+1]; $i++ } }
        "--research" { } # Backward-compatible no-op: there is only one UI.
        "--no-frontend" { $Frontend = 0 }
        "--dev" { $DevMode = 1 }
        "--rebuild" { $Rebuild = 1 }
        "--build" { $Rebuild = 1 }
        "-h" { "usage: see header"; exit 0 }
        "--help" { "usage: see header"; exit 0 }
        default { Die "unknown argument: $a" }
    }
    $i++
}
if ($LogsName -eq "research") { $LogsName = "frontend" }
if ($LogsName -eq "research-build") { $LogsName = "frontend-build" }
if ($LogsName -notin @("engine", "frontend", "frontend-build")) { Die "unknown log: $LogsName" }

function PidAlive($pidfile) {
    if (!(Test-Path $pidfile)) { return $false }
    $procPid = ([string](Get-Content $pidfile -ErrorAction SilentlyContinue | Select-Object -First 1)).Trim()
    if ([string]::IsNullOrWhiteSpace($procPid)) { return $false }
    $p = Get-Process -Id $procPid -ErrorAction SilentlyContinue
    return ($null -ne $p)
}

function Start-Bg($name, $dir, $cmd) {
    $pidfile = Join-Path $RunDir "$name.pid"
    $log = Join-Path $LogDir "$name.log"
    if (PidAlive $pidfile) {
        Warn "$name already running (pid $(Get-Content $pidfile))"
        return 0
    }
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $inner = "cd /d `"$dir`" && $cmd > `"$log`" 2>&1"
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $inner -PassThru -WindowStyle Hidden
    $proc.Id | Set-Content $pidfile
    Start-Sleep -Seconds 1
    if (PidAlive $pidfile) {
        Ok "$name started (pid $(Get-Content $pidfile), log .run/logs/$name.log)"
    } else {
        Warn "$name exited immediately - last lines:"
        if (Test-Path $log) { Get-Content $log -Tail 15 | ForEach-Object { Say "    $_" } }
        return 1
    }
    return 0
}

function Test-Health($url) {
    try {
        $body = Invoke-RestMethod -Uri $url -TimeoutSec 2 -ErrorAction Stop
        if ($url -eq $FrontendHealth) { return ($body.adapter -eq $true -and $body.engine -eq $true) }
        return ($body.status -eq "ok")
    } catch { return $false }
}

function Wait-For($url, $limit, $label) {
    $deadline = (Get-Date).AddSeconds($limit)
    do {
        if (Test-Health $url) { Ok "$label is up: $url"; return $true }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Ensure-Python {
    if (-not $env:WBALC_PYTHON -and !(Test-Path -LiteralPath $Python -PathType Leaf)) {
        if (!(Get-Command python.exe -ErrorAction SilentlyContinue)) { Die "Python is required; install it or set WBALC_PYTHON to an interpreter path" }
        & python.exe -m venv (Join-Path $Root ".venv")
        if ($LASTEXITCODE -ne 0) { Die "Could not create .venv" }
    }
    $interpreter = Get-Command $Python -CommandType Application -ErrorAction SilentlyContinue
    if (!$interpreter) { Die "Python not found: $Python" }
    $script:Python = $interpreter.Source
    & $Python -c "import uvicorn, fastapi, rasterio, sklearn, lightgbm, sqlalchemy" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Say "installing Python requirements"
        & $Python -m pip install -r (Join-Path $Root "requirements.txt")
        if ($LASTEXITCODE -ne 0) { Die "Python dependencies could not be installed; use a Python version supported by the requirements or set WBALC_PYTHON" }
    }
}

function Ensure-Node($dir) {
    if (!(Get-Command node.exe -ErrorAction SilentlyContinue) -or !(Get-Command npm.cmd -ErrorAction SilentlyContinue)) { Die "Node.js and npm are required for the workspace" }
    $nodeVersion = & node.exe --version
    $packageHash = (Get-FileHash (Join-Path $dir "package.json")).Hash
    $lockHash = (Get-FileHash (Join-Path $dir "package-lock.json")).Hash
    $fingerprint = "$nodeVersion $packageHash $lockHash"
    $stamp = Join-Path $dir "node_modules\.wbalc-deps-windows"
    $previous = Get-Content -LiteralPath $stamp -ErrorAction SilentlyContinue
    if ($previous -ne $fingerprint) {
        Say "synchronizing locked dependencies in frontend/"
        Push-Location $dir
        try {
            & npm.cmd ci --include=dev --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { Die "frontend dependency installation failed" }
            Set-Content -LiteralPath $stamp -Value $fingerprint -ErrorAction Stop
        } finally { Pop-Location }
    }
}

function Cmd-Up {
    foreach ($port in @($ApiPort, $FrontendPort)) {
        if ($port -notmatch '^[0-9]{1,5}$' -or [int]$port -lt 1 -or [int]$port -gt 65535) { Die "Invalid port: $port" }
    }
    New-Item -ItemType Directory -Force -Path $RunDir, $LogDir | Out-Null
    if (Test-Health $EngineHealth) {
        Ok "engine already answering on :$ApiPort (reusing it)"
    } else {
        Ensure-Python
        Say "starting engine on :$ApiPort"
        $reload = if ($DevMode) { " --reload" } else { "" }
        if ((Start-Bg engine $Root "`"$Python`" -m uvicorn app.main:app --host 0.0.0.0 --port $ApiPort$reload") -ne 0 -or !(Wait-For $EngineHealth 45 "engine")) {
            Die "engine failed to start: see .run/logs/engine.log"
        }
    }

    if ($Frontend) {
        if (Test-Health $FrontendHealth) {
            if ($Rebuild) { Die "Workspace already running. Run down before rebuilding." }
            Ok "SvelteKit workspace already answering on :$FrontendPort (reusing it)"
        } else {
            Ensure-Node $FrontendDir
            $common = "set `"RSAL_API_URL=http://127.0.0.1:$ApiPort`" && set `"PORT=$FrontendPort`""
            if ($DevMode) {
                $cmd = "$common && npm.cmd run dev -- --port $FrontendPort --strictPort"
            } else {
                Say "building SvelteKit workspace"
                $buildLog = Join-Path $LogDir "frontend-build.log"
                Push-Location $FrontendDir
                try {
                    & npm.cmd run build > $buildLog 2>&1
                    if ($LASTEXITCODE -ne 0) { Die "SvelteKit build failed: see .run/logs/frontend-build.log" }
                } finally { Pop-Location }
                $origin = if ($env:ORIGIN) { $env:ORIGIN } else { "http://localhost:$FrontendPort" }
                $bodyLimit = if ($env:BODY_SIZE_LIMIT) { $env:BODY_SIZE_LIMIT } else { "545259520" }
                $cmd = "$common && set `"HOST=0.0.0.0`" && set `"ORIGIN=$origin`" && set `"BODY_SIZE_LIMIT=$bodyLimit`" && node.exe build"
            }
            if ((Start-Bg frontend $FrontendDir $cmd) -ne 0 -or !(Wait-For $FrontendHealth 60 "SvelteKit workspace")) {
                Die "workspace failed to start or reach the engine: see .run/logs/frontend.log"
            }
        }
    }

    Say ""
    Say "  engine     http://localhost:$ApiPort/docs"
    if ($Frontend) { Say "  workspace  http://localhost:$FrontendPort" }
    Say 'logs:  .\scripts\up.ps1 logs [engine|frontend|frontend-build]'
    Say 'stop:  .\scripts\up.ps1 down'
}

function Cmd-Down {
    $found = $false
    Get-ChildItem (Join-Path $RunDir "*.pid") -ErrorAction SilentlyContinue | ForEach-Object {
        $name = $_.BaseName
        $procPid = ([string](Get-Content $_.FullName -ErrorAction SilentlyContinue | Select-Object -First 1)).Trim()
        if ($procPid -and (Get-Process -Id $procPid -ErrorAction SilentlyContinue)) {
            & taskkill /T /F /PID $procPid 2>$null | Out-Null
            Ok "stopped $name (pid $procPid)"
            $found = $true
        } else {
            Warn "$name was not running"
        }
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
    }
    if (-not $found) { Warn "nothing to stop (no live pid files in .run/)" }
    if (Test-Health $EngineHealth) { Warn "something is still serving :$ApiPort - it was not started by this script" }
}

function Cmd-Status {
    Say ""
    if (Test-Health $EngineHealth) { Ok "engine    :$ApiPort  up" } else { Warn "engine    :$ApiPort  down" }
    if (Test-Health $FrontendHealth) { Ok "workspace :$FrontendPort  up" } else { Warn "workspace :$FrontendPort  down or disconnected" }
    Say ""
    if (Test-Path $RunDir) {
        $pids = Get-ChildItem (Join-Path $RunDir "*.pid") -ErrorAction SilentlyContinue
        if ($pids) {
            foreach ($pf in $pids) { Write-Host ("  {0,-10} pid {1}" -f $pf.BaseName, (Get-Content $pf.FullName)) }
        } else { Say "  no pid files under .run/ (nothing started by up.ps1)" }
    }
    Say ""
}

function Cmd-Logs($name) {
    $log = Join-Path $LogDir "$name.log"
    if (!(Test-Path $log)) { Die "no log for '$name' (available: $((Get-ChildItem $LogDir -Filter *.log -ErrorAction SilentlyContinue | ForEach-Object { $_.BaseName }) -join ' '))" }
    Get-Content $log -Wait -Tail 200
}

switch ($Command) {
    "up" { Cmd-Up }
    "down" { Cmd-Down }
    "status" { Cmd-Status }
    "logs" { Cmd-Logs $LogsName }
    default { Die "unknown command: $Command" }
}
