<#
.SYNOPSIS
    SettleTable Windows Host Lifecycle Controller.

.DESCRIPTION
    Provides interactive menu and non-interactive command-line actions to safely start,
    stop, and monitor SettleTable services using Docker Compose. Supports both local-only
    development/inspection and public on-demand hosting via Cloudflare Named Tunnel.

.PARAMETER Action
    The action to execute: 'start-local', 'start-public', 'stop-public', 'stop-all', 'status', 'help'.
    If omitted, an interactive menu is displayed.

.EXAMPLE
    .\tools\SettleTable-Control.ps1
    Displays interactive selection menu.

.EXAMPLE
    .\tools\SettleTable-Control.ps1 start-local
    Starts local container (127.0.0.1:8000) and ensures Cloudflare tunnel is stopped.

.EXAMPLE
    .\tools\SettleTable-Control.ps1 start-public
    Verifies real-data volume and activates public HTTPS (https://settle.kybuilds.com).

.EXAMPLE
    .\tools\SettleTable-Control.ps1 stop-public
    Stops Cloudflare connector while preserving local application access.

.EXAMPLE
    .\tools\SettleTable-Control.ps1 stop-all
    Stops application and tunnel, preserving all data volumes, databases, and receipts.

.EXAMPLE
    .\tools\SettleTable-Control.ps1 status
    Displays container states, local health probe, and public edge status.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $false)]
    [string]$Action = "",

    [Alias("h")]
    [switch]$Help,

    [string]$DockerCmd = "docker",
    [string]$CurlCmd = "",
    [string]$PreflightCmd = "",
    [int]$MaxProbeAttempts = 15,
    [int]$ProbeIntervalSec = 1,
    [switch]$SkipPreflight
)

# Set strict error behavior for the script
$ErrorActionPreference = "Continue"

if ($env:SETTLETABLE_MAX_PROBE_ATTEMPTS) {
    $MaxProbeAttempts = [int]$env:SETTLETABLE_MAX_PROBE_ATTEMPTS
}
if ($env:SETTLETABLE_PROBE_INTERVAL_SEC) {
    $ProbeIntervalSec = [int]$env:SETTLETABLE_PROBE_INTERVAL_SEC
}

if ($Help) {
    Get-Help $MyInvocation.MyCommand.Path -Detailed
    exit 0
}

# Resolve repository root relative to script location
$ScriptPath = $MyInvocation.MyCommand.Path
if (-not $ScriptPath) {
    $ScriptDir = $PSScriptRoot
} else {
    $ScriptDir = Split-Path -Parent $ScriptPath
}
if (-not $ScriptDir) {
    $ScriptDir = "."
}
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

function Assert-DockerRunning {
    & $DockerCmd info >$null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n[ERROR] Docker daemon is not running or unreachable." -ForegroundColor Red
        Write-Host "Please start Docker Desktop on your Windows host and verify it is running.`n" -ForegroundColor Yellow
        return $false
    }
    return $true
}

function Get-RunningContainerIds {
    param(
        [string]$FilterName
    )
    $ids = & $DockerCmd ps --filter "name=$FilterName" --filter "status=running" -q 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $ids) {
        return @()
    }
    return ($ids -split "`r?`n") | Where-Object { $_.Trim() -ne "" }
}

function Get-EndpointStatusCode {
    param(
        [string]$Url,
        [int]$TimeoutSec = 4
    )
    $nullTarget = if ($env:OS -match "Windows_NT" -or (Get-Variable -Name IsWindows -ValueOnly -ErrorAction SilentlyContinue)) { "NUL" } else { "/dev/null" }
    $effectiveCurl = if ($CurlCmd) {
        $CurlCmd
    } elseif (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        "curl.exe"
    } else {
        "curl"
    }
    $code = & $effectiveCurl -s -o $nullTarget -w "%{http_code}" --max-time $TimeoutSec $Url 2>$null
    if ($code) {
        return $code.Trim()
    }
    return "000"
}

function Invoke-VolumePreFlight {
    param(
        [string]$Mode = "auto"
    )
    if ($SkipPreflight -or $env:SETTLETABLE_SKIP_PREFLIGHT -eq "1" -or $env:SETTLETABLE_SKIP_VOLUME_PREFLIGHT -eq "1") {
        Write-Host "Verifying storage volume configuration (--mode $Mode) [SKIPPED FOR TEST]..." -ForegroundColor Cyan
        return $true
    }

    Write-Host "Verifying storage volume configuration (--mode $Mode)..." -ForegroundColor Cyan
    if ($PreflightCmd) {
        $preflightOut = & $PreflightCmd --mode $Mode 2>&1
    } else {
        $verifyScript = Join-Path $RepoRoot (Join-Path "tools" "verify_volume_target.py")
        if (-not (Test-Path $verifyScript)) {
            Write-Host "[ERROR] Volume pre-flight utility not found: $verifyScript" -ForegroundColor Red
            return $false
        }

        $pythonBin = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }
        $preflightOut = & $pythonBin $verifyScript --mode $Mode 2>&1
    }
    if ($preflightOut) {
        Write-Host ($preflightOut -join "`n")
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n[ABORT] Storage volume pre-flight check failed! Review your .env configuration before starting." -ForegroundColor Red
        return $false
    }
    return $true
}

# ---------------------------------------------------------------------------
# Core Lifecycle Actions
# ---------------------------------------------------------------------------

function Invoke-StartLocal {
    if (-not (Assert-DockerRunning)) { return $false }

    # Step 1: Enforce public connector shutdown BEFORE volume pre-flight or app launch
    Write-Host "`n[1/3] Ensuring Cloudflare public connector is stopped..." -ForegroundColor Cyan
    $stopOut = & $DockerCmd compose stop cloudflared 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to execute docker compose stop cloudflared." -ForegroundColor Red
        if ($stopOut) { Write-Host ($stopOut -join "`n") -ForegroundColor Yellow }
        return $false
    }

    $tunnelRunning = @(Get-RunningContainerIds -FilterName "settletable_tunnel")
    if ($tunnelRunning.Count -gt 0) {
        Write-Host "[ERROR] Cloudflare tunnel container is still running after stop request. Aborting local mode." -ForegroundColor Red
        return $false
    }

    # Step 2: Validate volume configuration
    $volOk = Invoke-VolumePreFlight -Mode "auto"
    if ($volOk -ne $true) { return $false }

    # Step 3: Start application container
    Write-Host "[2/3] Starting SettleTable application container..." -ForegroundColor Cyan
    $upOut = & $DockerCmd compose up -d settletable 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to start settletable application container." -ForegroundColor Red
        if ($upOut) { Write-Host ($upOut -join "`n") -ForegroundColor Yellow }
        return $false
    }

    # Step 4: Verify local health probe
    Write-Host "[3/3] Waiting for local health probe (http://127.0.0.1:8000/healthz)..." -ForegroundColor Cyan
    $healthy = $false
    for ($i = 0; $i -lt $MaxProbeAttempts; $i++) {
        if ($ProbeIntervalSec -gt 0) { Start-Sleep -Seconds $ProbeIntervalSec }
        $code = Get-EndpointStatusCode -Url "http://127.0.0.1:8000/healthz" -TimeoutSec 2
        if ($code -eq "200") {
            $healthy = $true
            break
        }
    }

    if (-not $healthy) {
        Write-Host "`n[ERROR] Application container started but local health check did not return 200 within ${MaxProbeAttempts}s." -ForegroundColor Red
        Write-Host "Check container logs: $DockerCmd logs --tail 30 settletable_app" -ForegroundColor Yellow
        return $false
    }

    # Final fail-closed check: verify cloudflared is definitely not running
    $tunnelRunning = @(Get-RunningContainerIds -FilterName "settletable_tunnel")
    if ($tunnelRunning.Count -gt 0) {
        Write-Host "`n[CRITICAL] Cloudflare tunnel container is active! Stopping immediately to prevent unintentional public exposure." -ForegroundColor Red
        $null = & $DockerCmd compose stop cloudflared 2>&1
        return $false
    }

    Write-Host "`n=======================================================" -ForegroundColor Green
    Write-Host " [SUCCESS] SettleTable Local Server is Active" -ForegroundColor Green
    Write-Host "=======================================================" -ForegroundColor Green
    Write-Host " Local URL:      http://127.0.0.1:8000" -ForegroundColor White
    Write-Host " Public Ingress: STOPPED (cloudflared connector verified inactive)" -ForegroundColor Yellow
    Write-Host " Storage Mode:   Isolated Docker volume" -ForegroundColor White
    Write-Host "=======================================================`n" -ForegroundColor Green
    return $true
}

function Invoke-StartPublic {
    if (-not (Assert-DockerRunning)) { return $false }

    # Step 1: Pre-flight volume check (mode real)
    Write-Host "`n[PRE-FLIGHT] Verifying real-data volume configuration and permissions..." -ForegroundColor Cyan
    $volOk = Invoke-VolumePreFlight -Mode "real"
    if ($volOk -ne $true) { return $false }

    # Step 2: Start stack
    Write-Host "`n[1/4] Starting SettleTable application and Cloudflare tunnel connector..." -ForegroundColor Cyan
    $upOut = & $DockerCmd compose --profile with-cloudflared up -d 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to start Docker Compose stack." -ForegroundColor Red
        if ($upOut) { Write-Host ($upOut -join "`n") -ForegroundColor Yellow }
        return $false
    }

    # Step 3: Enforce local health probe before proceeding
    Write-Host "[2/4] Verifying local container health..." -ForegroundColor Cyan
    $localHealthy = $false
    for ($i = 0; $i -lt $MaxProbeAttempts; $i++) {
        if ($ProbeIntervalSec -gt 0) { Start-Sleep -Seconds $ProbeIntervalSec }
        $code = Get-EndpointStatusCode -Url "http://127.0.0.1:8000/healthz" -TimeoutSec 2
        if ($code -eq "200") {
            $localHealthy = $true
            break
        }
    }

    if (-not $localHealthy) {
        Write-Host "`n[ERROR] Local application health check failed (http://127.0.0.1:8000/healthz did not return 200 within ${MaxProbeAttempts}s)." -ForegroundColor Red
        Write-Host "Check application logs with: $DockerCmd logs --tail 30 settletable_app" -ForegroundColor Yellow
        Write-Host "Stopping Cloudflare tunnel connector to prevent exposing an unhealthy application..." -ForegroundColor Yellow
        $null = & $DockerCmd compose stop cloudflared 2>&1
        return $false
    }

    # Step 4: Verify tunnel connector container is running
    Write-Host "[3/4] Verifying Cloudflare tunnel connector container..." -ForegroundColor Cyan
    $tunnelRunning = @(Get-RunningContainerIds -FilterName "settletable_tunnel")
    if ($tunnelRunning.Count -eq 0) {
        Write-Host "[ERROR] Cloudflare tunnel container settletable_tunnel is not running." -ForegroundColor Red
        Write-Host "Check tunnel logs: $DockerCmd logs --tail 30 settletable_tunnel" -ForegroundColor Yellow
        return $false
    }

    # Step 5: Verify public edge HTTPS health
    Write-Host "[4/4] Verifying live public HTTPS endpoint (https://settle.kybuilds.com/healthz)..." -ForegroundColor Cyan
    $publicHealthy = $false
    for ($i = 0; $i -lt $MaxProbeAttempts; $i++) {
        if ($ProbeIntervalSec -gt 0) { Start-Sleep -Seconds $ProbeIntervalSec }
        $code = Get-EndpointStatusCode -Url "https://settle.kybuilds.com/healthz" -TimeoutSec 4
        if ($code -eq "200") {
            $publicHealthy = $true
            break
        }
    }

    if (-not $publicHealthy) {
        Write-Host "`n[ERROR] Cloudflare tunnel container is running, but public HTTPS endpoint did not return 200 within ${MaxProbeAttempts}s." -ForegroundColor Red
        Write-Host "Check tunnel logs with: $DockerCmd logs --tail 30 settletable_tunnel" -ForegroundColor Yellow
        return $false
    }

    Write-Host "`n=======================================================" -ForegroundColor Green
    Write-Host " [SUCCESS] SettleTable Live Public Service is Active" -ForegroundColor Green
    Write-Host "=======================================================" -ForegroundColor Green
    Write-Host " Public URL:     https://settle.kybuilds.com" -ForegroundColor White
    Write-Host " Local URL:      http://127.0.0.1:8000" -ForegroundColor White
    Write-Host " Tunnel Status:  Connected (settletable-pilot via Cloudflare)" -ForegroundColor Green
    Write-Host " Data Volume:    settletable_data (Production)" -ForegroundColor White
    Write-Host "=======================================================`n" -ForegroundColor Green
    return $true
}

function Invoke-StopPublic {
    if (-not (Assert-DockerRunning)) { return $false }

    Write-Host "`n[1/2] Stopping Cloudflare Named Tunnel connector..." -ForegroundColor Cyan
    $stopOut = & $DockerCmd compose stop cloudflared 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to execute docker compose stop cloudflared." -ForegroundColor Red
        if ($stopOut) { Write-Host ($stopOut -join "`n") -ForegroundColor Yellow }
        return $false
    }

    # Verify connector container is actually stopped
    $tunnelRunning = @(Get-RunningContainerIds -FilterName "settletable_tunnel")
    if ($tunnelRunning.Count -gt 0) {
        Write-Host "[ERROR] Cloudflare tunnel container settletable_tunnel is still running after stop command." -ForegroundColor Red
        return $false
    }

    Write-Host "[2/2] Checking public ingress deactivation..." -ForegroundColor Cyan
    $statusCode = Get-EndpointStatusCode -Url "https://settle.kybuilds.com/healthz" -TimeoutSec 5

    Write-Host "`n=======================================================" -ForegroundColor Yellow
    Write-Host " [STATUS] Cloudflare Public Ingress Stopped" -ForegroundColor Yellow
    Write-Host "=======================================================" -ForegroundColor Yellow
    Write-Host " Host Connector:  STOPPED (settletable_tunnel verified inactive)" -ForegroundColor Green

    if ($statusCode -eq "530") {
        Write-Host " Public Edge:     DISCONNECTED (Cloudflare edge confirmed: HTTP 530 Tunnel Inactive)" -ForegroundColor Green
    } elseif ($statusCode -eq "000") {
        Write-Host " Public Edge:     UNREACHABLE (Network timeout / connection closed)" -ForegroundColor Gray
    } elseif ($statusCode -eq "200") {
        Write-Host " Public Edge:     WARNING: Edge returned HTTP 200 (stale CDN cache or routing in-flight)" -ForegroundColor Yellow
    } else {
        Write-Host " Public Edge:     HTTP $statusCode" -ForegroundColor Yellow
    }

    # Verify local app state
    $localCode = Get-EndpointStatusCode -Url "http://127.0.0.1:8000/healthz" -TimeoutSec 2
    if ($localCode -eq "200") {
        Write-Host " Local App:       STILL ACTIVE & ACCESSIBLE (http://127.0.0.1:8000)" -ForegroundColor Cyan
    } else {
        Write-Host " Local App:       Stopped or unreachable (HTTP $localCode)" -ForegroundColor Gray
    }
    Write-Host "=======================================================`n" -ForegroundColor Yellow
    return $true
}

function Invoke-StopAll {
    if (-not (Assert-DockerRunning)) { return $false }

    Write-Host "`nStopping all SettleTable containers (preserving all volumes and data)..." -ForegroundColor Cyan
    $stopOut = & $DockerCmd compose --profile with-cloudflared stop 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to execute docker compose stop." -ForegroundColor Red
        if ($stopOut) { Write-Host ($stopOut -join "`n") -ForegroundColor Yellow }
        return $false
    }

    # Verify containers are actually stopped
    $appRunning = @(Get-RunningContainerIds -FilterName "settletable_app")
    $tunnelRunning = @(Get-RunningContainerIds -FilterName "settletable_tunnel")
    if ($appRunning.Count -gt 0 -or $tunnelRunning.Count -gt 0) {
        Write-Host "[ERROR] One or more SettleTable containers are still running after stop command." -ForegroundColor Red
        if ($appRunning.Count -gt 0) { Write-Host "  - settletable_app is still running" -ForegroundColor Red }
        if ($tunnelRunning.Count -gt 0) { Write-Host "  - settletable_tunnel is still running" -ForegroundColor Red }
        return $false
    }

    Write-Host "`n=======================================================" -ForegroundColor Cyan
    Write-Host " [STATUS] All SettleTable Containers Stopped" -ForegroundColor Cyan
    Write-Host "=======================================================" -ForegroundColor Cyan
    Write-Host " Container State: All containers stopped cleanly and verified inactive" -ForegroundColor White
    Write-Host " Data Safety:     All Docker volumes, SQLite databases, and receipt" -ForegroundColor Green
    Write-Host "                  photos remain intact and fully preserved." -ForegroundColor Green
    Write-Host " Reminder:        If you made real-meal changes during this session," -ForegroundColor Yellow
    Write-Host "                  remember to run the encrypted backup procedure to" -ForegroundColor Yellow
    Write-Host "                  Google Drive (docs/runbooks/windows_host_operations.md)." -ForegroundColor Yellow
    Write-Host "=======================================================`n" -ForegroundColor Cyan
    return $true
}

function Invoke-ShowStatus {
    if (-not (Assert-DockerRunning)) { return $false }

    Write-Host "`n=======================================================" -ForegroundColor Cyan
    Write-Host " SettleTable Environment & Container Status" -ForegroundColor Cyan
    Write-Host "=======================================================" -ForegroundColor Cyan

    Write-Host "Container Instances:" -ForegroundColor White
    $psOut = & $DockerCmd compose --profile with-cloudflared ps 2>&1
    if ($psOut) { Write-Host ($psOut -join "`n") }

    Write-Host "`nEndpoint Health Probes:" -ForegroundColor White
    $localCode = Get-EndpointStatusCode -Url "http://127.0.0.1:8000/healthz" -TimeoutSec 2
    if ($localCode -eq "200") {
        Write-Host "  * Local Ingress (127.0.0.1:8000):    HEALTHY (200 OK)" -ForegroundColor Green
    } else {
        Write-Host "  * Local Ingress (127.0.0.1:8000):    OFFLINE / STOPPED (HTTP $localCode)" -ForegroundColor Gray
    }

    $publicCode = Get-EndpointStatusCode -Url "https://settle.kybuilds.com/healthz" -TimeoutSec 4
    if ($publicCode -eq "200") {
        Write-Host "  * Public Edge (settle.kybuilds.com):  ACTIVE / REACHABLE (200 OK)" -ForegroundColor Green
    } elseif ($publicCode -eq "530") {
        Write-Host "  * Public Edge (settle.kybuilds.com):  DISCONNECTED (HTTP 530 Tunnel Offline)" -ForegroundColor Gray
    } elseif ($publicCode -eq "000") {
        Write-Host "  * Public Edge (settle.kybuilds.com):  UNREACHABLE (Network Timeout / Offline)" -ForegroundColor Gray
    } else {
        Write-Host "  * Public Edge (settle.kybuilds.com):  HTTP $publicCode" -ForegroundColor Yellow
    }

    Write-Host "`nConfigured Data Volume Target:" -ForegroundColor White
    $envPath = Join-Path $RepoRoot ".env"
    if (Test-Path $envPath) {
        $volLine = Get-Content $envPath | Where-Object { $_ -match "^SETTLETABLE_DATA_VOLUME=" }
        if ($volLine) {
            Write-Host "  * $volLine" -ForegroundColor White
        } else {
            Write-Host "  * SETTLETABLE_DATA_VOLUME=settletable_data (Default)" -ForegroundColor Gray
        }
    } else {
        Write-Host "  * SETTLETABLE_DATA_VOLUME=settletable_data (Default, no .env file)" -ForegroundColor Gray
    }
    Write-Host "=======================================================`n" -ForegroundColor Cyan
    return $true
}

function Show-InteractiveMenu {
    while ($true) {
        Write-Host "`n=======================================================" -ForegroundColor Cyan
        Write-Host " SettleTable Windows Host Lifecycle Controller" -ForegroundColor Cyan
        Write-Host "=======================================================" -ForegroundColor Cyan
        Write-Host " [1] Start Local   - Start app on 127.0.0.1:8000 (tunnel stopped)" -ForegroundColor White
        Write-Host " [2] Start Public  - Start app + Cloudflare tunnel (https://settle.kybuilds.com)" -ForegroundColor White
        Write-Host " [3] Stop Public   - Stop tunnel only (app remains accessible locally)" -ForegroundColor White
        Write-Host " [4] Stop All      - Stop both app and tunnel (preserve data)" -ForegroundColor White
        Write-Host " [5] Status        - Check container states and health probes" -ForegroundColor White
        Write-Host " [Q] Quit" -ForegroundColor Gray
        Write-Host "=======================================================" -ForegroundColor Cyan

        $choice = Read-Host "Select an option [1-5, Q]"
        if (-not $choice) { continue }
        switch ($choice.Trim().ToUpper()) {
            "1" { [void](Invoke-StartLocal) }
            "2" { [void](Invoke-StartPublic) }
            "3" { [void](Invoke-StopPublic) }
            "4" { [void](Invoke-StopAll) }
            "5" { [void](Invoke-ShowStatus) }
            "Q" { Write-Host "Goodbye!`n"; return }
            default { Write-Host "Invalid selection. Please choose 1, 2, 3, 4, 5, or Q." -ForegroundColor Yellow }
        }
    }
}

# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

Push-Location $RepoRoot
try {
    switch ($Action.Trim().ToLower()) {
        "start-local"   { $ok = Invoke-StartLocal; if ($ok -ne $true) { exit 1 } }
        "local"         { $ok = Invoke-StartLocal; if ($ok -ne $true) { exit 1 } }
        "start-public"  { $ok = Invoke-StartPublic; if ($ok -ne $true) { exit 1 } }
        "public"        { $ok = Invoke-StartPublic; if ($ok -ne $true) { exit 1 } }
        "stop-public"   { $ok = Invoke-StopPublic; if ($ok -ne $true) { exit 1 } }
        "disconnect"    { $ok = Invoke-StopPublic; if ($ok -ne $true) { exit 1 } }
        "stop-all"      { $ok = Invoke-StopAll; if ($ok -ne $true) { exit 1 } }
        "stop"          { $ok = Invoke-StopAll; if ($ok -ne $true) { exit 1 } }
        "status"        { $ok = Invoke-ShowStatus; if ($ok -ne $true) { exit 1 } }
        "info"          { $ok = Invoke-ShowStatus; if ($ok -ne $true) { exit 1 } }
        "help"          { Get-Help $MyInvocation.MyCommand.Path -Detailed; exit 0 }
        "-h"            { Get-Help $MyInvocation.MyCommand.Path -Detailed; exit 0 }
        "/?"            { Get-Help $MyInvocation.MyCommand.Path -Detailed; exit 0 }
        ""              { Show-InteractiveMenu }
        default {
            Write-Host "Unknown action: '$Action'" -ForegroundColor Red
            Write-Host "Usage: .\tools\SettleTable-Control.ps1 [start-local | start-public | stop-public | stop-all | status | help]" -ForegroundColor Yellow
            exit 1
        }
    }
} finally {
    Pop-Location
}
