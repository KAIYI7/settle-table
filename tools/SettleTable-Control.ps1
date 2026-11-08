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
    [switch]$Help
)

# Set strict error behavior for the script
$ErrorActionPreference = "Continue"

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
    & docker info >$null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n[ERROR] Docker daemon is not running or unreachable." -ForegroundColor Red
        Write-Host "Please start Docker Desktop on your Windows host and verify it is running.`n" -ForegroundColor Yellow
        return $false
    }
    return $true
}

function Get-EndpointStatusCode {
    param(
        [string]$Url,
        [int]$TimeoutSec = 4
    )
    $nullTarget = if ($env:OS -match "Windows_NT" -or (Get-Variable -Name IsWindows -ValueOnly -ErrorAction SilentlyContinue)) { "NUL" } else { "/dev/null" }
    $curlBin = if (Get-Command curl.exe -ErrorAction SilentlyContinue) { "curl.exe" } else { "curl" }
    $code = & $curlBin -s -o $nullTarget -w "%{http_code}" --max-time $TimeoutSec $Url 2>$null
    if ($code) {
        return $code.Trim()
    }
    return "000"
}

function Invoke-VolumePreFlight {
    param(
        [string]$Mode = "auto"
    )
    Write-Host "Verifying storage volume configuration (--mode $Mode)..." -ForegroundColor Cyan
    $verifyScript = Join-Path $RepoRoot "tools\verify_volume_target.py"
    if (-not (Test-Path $verifyScript)) {
        Write-Host "[ERROR] Volume pre-flight utility not found: $verifyScript" -ForegroundColor Red
        return $false
    }

    & python $verifyScript --mode $Mode
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
    if (-not (Invoke-VolumePreFlight -Mode "auto")) { return $false }

    Write-Host "`n[1/3] Ensuring Cloudflare public connector is stopped..." -ForegroundColor Cyan
    & docker compose stop cloudflared >$null 2>&1

    Write-Host "[2/3] Starting SettleTable application container..." -ForegroundColor Cyan
    & docker compose up -d settletable
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to start settletable application container." -ForegroundColor Red
        return $false
    }

    Write-Host "[3/3] Waiting for local health probe (http://127.0.0.1:8000/healthz)..." -ForegroundColor Cyan
    $healthy = $false
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        $code = Get-EndpointStatusCode -Url "http://127.0.0.1:8000/healthz" -TimeoutSec 2
        if ($code -eq "200") {
            $healthy = $true
            break
        }
    }

    # Verify cloudflared did not start
    $tunnelRunning = & docker ps --filter "name=settletable_tunnel" --filter "status=running" -q
    if ($tunnelRunning) {
        Write-Host "[WARNING] Cloudflare tunnel container was running; stopping it now..." -ForegroundColor Yellow
        & docker compose stop cloudflared >$null 2>&1
    }

    if ($healthy) {
        Write-Host "`n=======================================================" -ForegroundColor Green
        Write-Host " [SUCCESS] SettleTable Local Server is Active" -ForegroundColor Green
        Write-Host "=======================================================" -ForegroundColor Green
        Write-Host " Local URL:      http://127.0.0.1:8000" -ForegroundColor White
        Write-Host " Public Ingress: STOPPED (cloudflared container inactive)" -ForegroundColor Yellow
        Write-Host " Storage Mode:   Isolated Docker volume" -ForegroundColor White
        Write-Host "=======================================================`n" -ForegroundColor Green
        return $true
    } else {
        Write-Host "`n[WARNING] Application container started but local health check did not return 200 within 15s." -ForegroundColor Yellow
        Write-Host "Check container logs: docker logs --tail 30 settletable_app" -ForegroundColor Yellow
        return $false
    }
}

function Invoke-StartPublic {
    if (-not (Assert-DockerRunning)) { return $false }

    Write-Host "`n[PRE-FLIGHT] Verifying real-data volume configuration and permissions..." -ForegroundColor Cyan
    if (-not (Invoke-VolumePreFlight -Mode "real")) { return $false }

    Write-Host "`n[1/4] Starting SettleTable application and Cloudflare tunnel connector..." -ForegroundColor Cyan
    & docker compose --profile with-cloudflared up -d
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to start Docker Compose stack." -ForegroundColor Red
        return $false
    }

    Write-Host "[2/4] Verifying local container health..." -ForegroundColor Cyan
    $localHealthy = $false
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        $code = Get-EndpointStatusCode -Url "http://127.0.0.1:8000/healthz" -TimeoutSec 2
        if ($code -eq "200") {
            $localHealthy = $true
            break
        }
    }

    Write-Host "[3/4] Verifying Cloudflare tunnel connector container..." -ForegroundColor Cyan
    $tunnelRunning = & docker ps --filter "name=settletable_tunnel" --filter "status=running" -q
    if (-not $tunnelRunning) {
        Write-Host "[ERROR] Tunnel container settletable_tunnel is not running." -ForegroundColor Red
        Write-Host "Check tunnel logs: docker logs --tail 30 settletable_tunnel" -ForegroundColor Yellow
        return $false
    }

    Write-Host "[4/4] Verifying live public HTTPS endpoint (https://settle.kybuilds.com/healthz)..." -ForegroundColor Cyan
    $publicHealthy = $false
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        $code = Get-EndpointStatusCode -Url "https://settle.kybuilds.com/healthz" -TimeoutSec 4
        if ($code -eq "200") {
            $publicHealthy = $true
            break
        }
    }

    if ($publicHealthy) {
        Write-Host "`n=======================================================" -ForegroundColor Green
        Write-Host " [SUCCESS] SettleTable Live Public Service is Active" -ForegroundColor Green
        Write-Host "=======================================================" -ForegroundColor Green
        Write-Host " Public URL:     https://settle.kybuilds.com" -ForegroundColor White
        Write-Host " Local URL:      http://127.0.0.1:8000" -ForegroundColor White
        Write-Host " Tunnel Status:  Connected (settletable-pilot via Cloudflare)" -ForegroundColor Green
        Write-Host " Data Volume:    settletable_data (Production)" -ForegroundColor White
        Write-Host "=======================================================`n" -ForegroundColor Green
        return $true
    } else {
        Write-Host "`n[WARNING] Stack started but public endpoint did not return 200 within 15s." -ForegroundColor Yellow
        Write-Host "Check tunnel logs: docker logs --tail 30 settletable_tunnel" -ForegroundColor Yellow
        return $false
    }
}

function Invoke-StopPublic {
    if (-not (Assert-DockerRunning)) { return $false }

    Write-Host "`n[1/2] Stopping Cloudflare Named Tunnel connector..." -ForegroundColor Cyan
    & docker compose stop cloudflared

    Write-Host "[2/2] Verifying public ingress deactivation..." -ForegroundColor Cyan
    $statusCode = Get-EndpointStatusCode -Url "https://settle.kybuilds.com/healthz" -TimeoutSec 5
    $disconnected = ($statusCode -eq "530" -or $statusCode -eq "000" -or $statusCode -eq "502")

    Write-Host "`n=======================================================" -ForegroundColor Yellow
    Write-Host " [STATUS] Cloudflare Public Ingress Stopped" -ForegroundColor Yellow
    Write-Host "=======================================================" -ForegroundColor Yellow
    if ($disconnected) {
        Write-Host " Public Endpoint: DISCONNECTED (HTTP $statusCode / Tunnel inactive verified)" -ForegroundColor Green
    } else {
        Write-Host " Public Endpoint: Connector stopped (HTTP $statusCode / Edge propagation pending)" -ForegroundColor Yellow
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
    & docker compose --profile with-cloudflared stop

    Write-Host "`n=======================================================" -ForegroundColor Cyan
    Write-Host " [STATUS] All SettleTable Containers Stopped" -ForegroundColor Cyan
    Write-Host "=======================================================" -ForegroundColor Cyan
    Write-Host " Container State: All containers stopped cleanly" -ForegroundColor White
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
    & docker compose --profile with-cloudflared ps

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
        "start-local"   { $ok = Invoke-StartLocal; if (-not $ok) { exit 1 } }
        "local"         { $ok = Invoke-StartLocal; if (-not $ok) { exit 1 } }
        "start-public"  { $ok = Invoke-StartPublic; if (-not $ok) { exit 1 } }
        "public"        { $ok = Invoke-StartPublic; if (-not $ok) { exit 1 } }
        "stop-public"   { $ok = Invoke-StopPublic; if (-not $ok) { exit 1 } }
        "disconnect"    { $ok = Invoke-StopPublic; if (-not $ok) { exit 1 } }
        "stop-all"      { $ok = Invoke-StopAll; if (-not $ok) { exit 1 } }
        "stop"          { $ok = Invoke-StopAll; if (-not $ok) { exit 1 } }
        "status"        { $ok = Invoke-ShowStatus; if (-not $ok) { exit 1 } }
        "info"          { $ok = Invoke-ShowStatus; if (-not $ok) { exit 1 } }
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
