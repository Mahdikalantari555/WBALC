# Run the whole stack natively on Windows (PowerShell port of scripts/up.sh).
#   .\scripts\up.ps1 up                engine :8000 + Next.js workspace :3000
#   .\scripts\up.ps1 up --research     ... plus SvelteKit research workspace :5173
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
$ResearchPort = if ($env:RESEARCH_PORT) { $env:RESEARCH_PORT } else { "5173" }

$Python = "D:\Dev\Miniforge3\envs\geo\python.exe"
if (!(Test-Path $Python)) { $Python = "python" }

function Say($m) { Write-Host $m }
function Ok($m) { Write-Host "[OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Die($m) { Write-Host "[X] $m" -ForegroundColor Red; exit 1 }

# ---- arg parsing ----
$Command = ""
$ResearchUi = 0
$NextUi = 1
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
        "--research" { $ResearchUi = 1 }
        "--no-frontend" { $NextUi = 0 }
        "--dev" { $DevMode = 1 }
        "--rebuild" { $Rebuild = 1 }
        "--build" { $Rebuild = 1 }
        "-h" { "usage: see header"; exit 0 }
        "--help" { "usage: see header"; exit 0 }
        default { Die "unknown argument: $a" }
    }
    $i++
}
if ([string]::IsNullOrWhiteSpace($Command)) { Die "missing command (up|down|status|logs)" }

function PidAlive($pidfile) {
    if (!(Test-Path $pidfile)) { return $false }
    $procPid = (Get-Content $pidfile -ErrorAction SilentlyContinue | Select-Object -First 1).ToString().Trim()
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
        if (Test-Path $log) { Get-Content $log -Tail 15 | ForEach-Object { "    $_" } }
        return 1
    }
    return 0
}

function Wait-For($url, $limit, $label) {
    $waited = 0
    while ($true) {
        & curl.exe -fsS -m 2 $url 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { Ok "$label is up: $url"; return $true }
        $waited++
        if ($waited -ge $limit) { Warn "$label did not answer $url within ${limit}s"; return $false }
        Start-Sleep -Seconds 1
    }
}

function Ensure-Venv {
    if (!(Test-Path $Python)) { Die "python not found: $Python" }
    & $Python -c "import fastapi, rasterio, sklearn, lightgbm" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Say "installing python requirements (first run only)"
        & $Python -m pip install -q -r (Join-Path $Root "requirements.txt")
    }
}

function Ensure-Node($dir) {
    if (!(Get-Command npm -ErrorAction SilentlyContinue)) { Die "npm is required for the UI services" }
    if (!(Test-Path (Join-Path $dir "node_modules")) -or !(Test-Path (Join-Path $dir "node_modules\.bin"))) {
        Say "installing node modules in $($dir.Substring($Root.Length+1))"
        Push-Location $dir
        & npm ci --no-audit --no-fund *>$null
        if ($LASTEXITCODE -ne 0) { & npm install --no-audit --no-fund *>$null }
        Pop-Location
    }
}

function Cmd-Up {
    New-Item -ItemType Directory -Force -Path $RunDir, $LogDir | Out-Null

    # ---- engine ----
    & curl.exe -fsS -m 1 "http://localhost:$ApiPort/health" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Ok "engine already answering on :$ApiPort (reusing it)"
    } else {
        Ensure-Venv
        Say "starting engine on :$ApiPort"
        if ($DevMode -eq 1) {
            Start-Bg engine $Root "$Python -m uvicorn app.main:app --host 0.0.0.0 --port $ApiPort --reload" | Out-Null
        } else {
            Start-Bg engine $Root "$Python -m uvicorn app.main:app --host 0.0.0.0 --port $ApiPort" | Out-Null
        }
        $ok = Wait-For "http://localhost:$ApiPort/health" 45 "engine"
        if (-not $ok) { Die "engine failed to start: see .run/logs/engine.log" }
    }

    # ---- next.js UI ----
    if ($NextUi -eq 1) {
        & curl.exe -fsS -m 1 "http://localhost:$FrontendPort/" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Ok "Next.js workspace already answering on :$FrontendPort (reusing it)"
        } else {
            Ensure-Node (Join-Path $Root "frontend")
            $standalone = Join-Path $Root "frontend\.next\standalone"
            $standaloneServer = Join-Path $standalone "server.js"
            if ($Rebuild -eq 1 -or !(Test-Path $standaloneServer)) {
                Say "building Next.js workspace"
                $buildLog = Join-Path $LogDir "frontend-build.log"
                $env:BUILD_STANDALONE = "1"
                Push-Location (Join-Path $Root "frontend")
                & npm run build -- --webpack > $buildLog 2>&1
                $bexit = $LASTEXITCODE
                Pop-Location
                Remove-Item Env:BUILD_STANDALONE -ErrorAction SilentlyContinue
                if ($bexit -ne 0) { Die "Next.js build failed: see .run/logs/frontend-build.log" }
                $staticSrc = Join-Path $Root "frontend\.next\static"
                $staticDst = Join-Path $standalone ".next\static"
                if (Test-Path $staticSrc) { Copy-Item -Recurse -Force $staticSrc $staticDst -ErrorAction SilentlyContinue }
                $pubSrc = Join-Path $Root "frontend\public"
                $pubDst = Join-Path $standalone "public"
                if (Test-Path $pubSrc) { Copy-Item -Recurse -Force $pubSrc $pubDst -ErrorAction SilentlyContinue }
            } else {
                Say "frontend build exists, skipping (use --rebuild to rebuild)"
            }
            $standalone = Join-Path $Root "frontend\.next\standalone"
            $cmd = "set `"PORT=$FrontendPort`" && set `"HOSTNAME=0.0.0.0`" && set `"NODE_ENV=production`" && set `"RSAL_API_URL=http://localhost:$ApiPort`" && node server.js"
            Start-Bg frontend $standalone $cmd | Out-Null
            Wait-For "http://localhost:$FrontendPort/" 60 "Next.js workspace" | Out-Null
        }
    }

    # ---- research workspace ----
    if ($ResearchUi -eq 1) {
        & curl.exe -fsS -m 1 "http://localhost:$ResearchPort/" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Ok "research workspace already answering on :$ResearchPort (reusing it)"
        } else {
            $dir = Join-Path $Root "examples\wbalc-geospatial-research-interface"
            Ensure-Node $dir
            if ($DevMode -eq 1) {
                $cmd = "set `"RSAL_API_URL=http://localhost:$ApiPort`" && set `"PORT=$ResearchPort`" && npx.cmd vite dev --host 0.0.0.0 --port $ResearchPort"
                Start-Bg research $dir $cmd | Out-Null
                Wait-For "http://localhost:$ResearchPort/" 60 "research workspace" | Out-Null
            } else {
                $researchBuild = Join-Path $dir "build"
                if ($Rebuild -eq 1 -or !(Test-Path (Join-Path $researchBuild "index.js"))) {
                    Say "building research workspace"
                    $rbuildLog = Join-Path $LogDir "research-build.log"
                    Push-Location $dir
                    & npm run build > $rbuildLog 2>&1
                    $rexit = $LASTEXITCODE
                    Pop-Location
                    if ($rexit -ne 0) { Die "research workspace build failed: see .run/logs/research-build.log" }
                } else {
                    Say "research build exists, skipping (use --rebuild to rebuild)"
                }
                $cmd = "set `"RSAL_API_URL=http://localhost:$ApiPort`" && set `"PORT=$ResearchPort`" && set `"HOST=0.0.0.0`" && node build"
                Start-Bg research $dir $cmd | Out-Null
                Wait-For "http://localhost:$ResearchPort/" 60 "research workspace" | Out-Null
            }
        }
    }

    Say ""
    Say "  engine     http://localhost:$ApiPort/docs"
    if ($NextUi -eq 1) { Say "  workspace  http://localhost:$FrontendPort" }
    if ($ResearchUi -eq 1) { Say "  research   http://localhost:$ResearchPort" }
    Say ""
    Say "logs:  .\scripts\up.ps1 logs [engine|frontend|research]"
    Say "stop:  .\scripts\up.ps1 down"
}

function Cmd-Down {
    $found = $false
    Get-ChildItem (Join-Path $RunDir "*.pid") -ErrorAction SilentlyContinue | ForEach-Object {
        $name = $_.BaseName
        $procPid = (Get-Content $_.FullName -ErrorAction SilentlyContinue | Select-Object -First 1).ToString().Trim()
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
    & curl.exe -fsS -m 1 "http://localhost:$ApiPort/health" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Warn "something is still serving :$ApiPort - it was not started by this script" }
}

function Cmd-Status {
    Say ""
    & curl.exe -fsS -m 2 "http://localhost:$ApiPort/health" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $h = & curl.exe -fsS -m 2 "http://localhost:$ApiPort/health" 2>$null
        Ok "engine    :$ApiPort  $h"
    } else { Warn "engine    :$ApiPort  down" }
    & curl.exe -fsS -m 2 "http://localhost:$FrontendPort/" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok "workspace :$FrontendPort  up" } else { Warn "workspace :$FrontendPort  down" }
    & curl.exe -fsS -m 2 "http://localhost:$ResearchPort/" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok "research  :$ResearchPort  up" } else { Warn "research  :$ResearchPort  down" }
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
