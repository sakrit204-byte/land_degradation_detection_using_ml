<#
CARE-EW one-click demo launcher (run through START_DEMO.bat in the repo root).

  1. finds or creates .venv and installs requirements.txt when the UI packages are missing
  2. checks app/static/data/aois.json (falls back to clearly-labelled MOCK data if absent)
  3. reuses a CARE-EW server that is already running, otherwise starts one on the first free port 8765-8775
  4. waits for /api/health, warms the data caches, opens the console in the browser
  5. keeps the PC and screen awake while the demo runs; closing the window or pressing Enter stops the server

Options:  -Port 8765   -Aoi NPL_chure (deep link)   -NoBrowser   -InstallShortcut (adds "CARE-EW Demo" to the Desktop)
#>
param([int]$Port = 8765, [string]$Aoi = "", [switch]$NoBrowser, [switch]$InstallShortcut)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
try { $Host.UI.RawUI.WindowTitle = "CARE-EW demo server" } catch {}

function Step($m) { Write-Host "[CARE-EW] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[CARE-EW] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[CARE-EW] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[CARE-EW] $m" -ForegroundColor Red; Read-Host "Press Enter to close" | Out-Null; exit 1 }

function Get-Health([int]$p) {
    try { return Invoke-RestMethod "http://127.0.0.1:$p/api/health" -TimeoutSec 2 } catch { return $null }
}
function Test-PortFree([int]$p) {
    return -not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

if ($InstallShortcut) {
    $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "CARE-EW Demo.lnk"
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $s.TargetPath = Join-Path $Root "START_DEMO.bat"
    $s.WorkingDirectory = $Root
    $s.IconLocation = "$env:SystemRoot\System32\imageres.dll,1"
    $s.Description = "Start the CARE-EW land-degradation early-warning console"
    $s.Save()
    Ok "Desktop shortcut created: $lnk"
}

Write-Host ""
Write-Host "  CARE-EW  |  satellite early warning of persistent land degradation" -ForegroundColor White
Write-Host ""

# ---------------------------------------------------------------- 1. Python environment
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Step "No .venv found - creating it (first run only, needs Python 3.11+)"
    $made = $false
    foreach ($cmd in @("py -3.11", "py -3", "python")) {
        $exe, $arg = $cmd.Split(" ", 2)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $a = @(); if ($arg) { $a += $arg }; $a += @("-m", "venv", ".venv")
        & $exe @a
        if ($LASTEXITCODE -eq 0 -and (Test-Path $Py)) { $made = $true; break }
    }
    if (-not $made) { Fail "Could not create .venv. Install Python 3.11 from python.org and run this again." }
}
& $Py -c "import fastapi, uvicorn, numpy, pyproj, pydantic" 2>$null
if ($LASTEXITCODE -ne 0) {
    Step "Installing Python packages from requirements.txt (first run only, several minutes)"
    & $Py -m pip install --upgrade pip
    & $Py -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Fail "pip install failed - check the internet connection and run this again." }
}
Ok "Python environment ready ($(& $Py --version))"

# ---------------------------------------------------------------- 2. data for the UI
$AoisJson = Join-Path $Root "app\static\data\aois.json"
if (-not (Test-Path $AoisJson)) {
    Warn "app/static/data/aois.json is missing (pipeline output not on this PC)."
    Warn "Writing MOCK demo data - the UI will show a purple 'MOCK DATA - not results' badge."
    & $Py app/make_mock_data.py
    if ($LASTEXITCODE -ne 0) { Fail "make_mock_data.py failed." }
}
New-Item -ItemType Directory -Force (Join-Path $Root "logs") | Out-Null

# ---------------------------------------------------------------- 3. server (reuse or start)
$server = $null
$h = Get-Health $Port
if ($h -and $h.status -eq "ok" -and $null -ne $h.aois_json) {
    Ok "CARE-EW server already running on port $Port - reusing it"
} else {
    if (-not (Test-PortFree $Port)) {
        $old = $Port
        $Port = (8765..8775 | Where-Object { Test-PortFree $_ } | Select-Object -First 1)
        if (-not $Port) { Fail "Ports 8765-8775 are all in use." }
        Warn "Port $old is used by another program - using port $Port instead"
    }
    Step "Starting the web server on http://127.0.0.1:$Port ..."
    $log = Join-Path $Root "logs\ui_server.log"; $err = Join-Path $Root "logs\ui_server.err.log"
    # -NoNewWindow keeps the server attached to this console, so closing the window stops it too
    $server = Start-Process -FilePath $Py -WorkingDirectory $Root -NoNewWindow -PassThru `
        -ArgumentList @("-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", "$Port") `
        -RedirectStandardOutput $log -RedirectStandardError $err
    $deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Milliseconds 500
        if ($server.HasExited) {
            Get-Content $err -Tail 25 -ErrorAction SilentlyContinue
            Fail "The server stopped during start-up (log above, full log in logs\ui_server.err.log)."
        }
        $h = Get-Health $Port
    } until ($h -or (Get-Date) -gt $deadline)
    if (-not $h) { Fail "The server did not answer within 90 s (see logs\ui_server.err.log)." }
    Ok "Server is up (PID $($server.Id))"
}

# ---------------------------------------------------------------- 4. checks, warm-up, browser
$keys = @($h.cubes.PSObject.Properties.Name)
$withCube = @($h.cubes.PSObject.Properties | Where-Object { $_.Value.cube }).Count
if ($h.mock_data) { Warn "Showing MOCK data (badge visible in the UI) - not results." }
else { Ok "Real pipeline output: $($keys.Count) areas, $withCube with pixel time series" }

foreach ($f in @("data/aois.json", "data/metrics.json")) {
    try { Invoke-WebRequest "http://127.0.0.1:$Port/$f" -UseBasicParsing -TimeoutSec 10 | Out-Null } catch {}
}
try {
    Invoke-WebRequest "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer?f=json" -UseBasicParsing -TimeoutSec 6 | Out-Null
    Ok "Internet OK (satellite base map reachable)"
} catch {
    Warn "Esri base-map server not reachable - the globe will have no background imagery."
    Warn "Overlays, charts, hotspots and the model card still work offline."
}

# keep the PC and the screen awake while this window is open (released automatically when it closes)
try {
    Add-Type -Namespace CareEw -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);'
    [CareEw.Power]::SetThreadExecutionState([uint32]2147483651) | Out-Null
    Ok "Sleep and screen-off are paused while the demo runs"
} catch {}

$Url = "http://127.0.0.1:$Port/"
if ($Aoi) { $Url += "#aoi=$Aoi" }
if (-not $NoBrowser) { Start-Process $Url }

Write-Host ""
Write-Host "  Console:  $Url" -ForegroundColor White
Write-Host "  Demo path: globe -> click an AOI pin (e.g. NPL_chure) -> risk layer + time slider ->"
Write-Host "             click a hotspot box (time-lapse) -> click the map (pixel inspector) ->"
Write-Host "             Analytics drawer -> Model card.  Draw box shows the on-demand planner"
Write-Host "             (avoid 'Run analysis' live: a real run takes ~45 min per block)."
Write-Host "  Logs:     logs\ui_server.log, logs\ui_server.err.log"
Write-Host ""

if (-not $server) { Read-Host "Server was already running; press Enter to close this window (it keeps running)" | Out-Null; exit 0 }
try {
    Read-Host "Press Enter (or close this window) to STOP the server" | Out-Null
} finally {
    if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
    Ok "Server stopped."
}
