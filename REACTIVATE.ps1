# ============================================================
# NovaBlock - REACTIVATE
# ============================================================
# Reverses EMERGENCY_RESET: turns the Windows Firewall back on,
# re-enables NovaBlock scheduled tasks, and launches NovaBlock.exe
# which will re-apply hosts block, DNS, firewall rules, browser
# policies, and persistence layers via its in-process watchdog.
#
# Usage:
#   1) Local: double-click REACTIVATE.bat (auto-elevates)
#   2) Remote: iex (irm https://raw.githubusercontent.com/novaiax/novablock-X/main/REACTIVATE.ps1)
# ============================================================

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

# Admin check
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "This script needs admin rights." -ForegroundColor Red
    Write-Host "Reopen PowerShell as Administrator and rerun." -ForegroundColor Yellow
    exit 1
}

Write-Host "=== REACTIVATE NOVABLOCK ===" -ForegroundColor Green

# 1. Turn Windows Firewall back ON
Write-Host "[1] Turning Windows Firewall back ON..." -ForegroundColor Cyan
netsh advfirewall set allprofiles state on | Out-Null
Write-Host "    OK" -ForegroundColor Green

# 2. Re-enable scheduled tasks
Write-Host "[2] Re-enabling NovaBlock scheduled tasks..." -ForegroundColor Cyan
schtasks /Change /TN NovaBlockWatchdog /Enable 2>$null | Out-Null
schtasks /Change /TN NovaBlockApp /Enable 2>$null | Out-Null
Write-Host "    OK" -ForegroundColor Green

# 3. Locate NovaBlock.exe
Write-Host "[3] Locating NovaBlock.exe..." -ForegroundColor Cyan
$exePath = $null
$candidates = @(
    "$env:LOCALAPPDATA\NovaBlock\NovaBlock.exe",
    "$env:PROGRAMFILES\NovaBlock\NovaBlock.exe",
    "${env:PROGRAMFILES(X86)}\NovaBlock\NovaBlock.exe",
    "D:\code\app\bloqueur distractions\dist\NovaBlock.exe",
    "D:\code\app\bloqueur distractions\dist-release\NovaBlock.exe"
)
foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) { $exePath = $c; break }
}
if (-not $exePath) {
    try {
        $regVal = (Get-ItemProperty -Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run' -Name NovaBlock -ErrorAction Stop).NovaBlock
        $candidate = $regVal.Trim('"')
        if (Test-Path $candidate) { $exePath = $candidate }
    } catch { }
}
if ($exePath) {
    Write-Host "    Found: $exePath" -ForegroundColor Green
} else {
    Write-Host "    NOT FOUND - install NovaBlock first via update.bat or the original installer." -ForegroundColor Red
    exit 1
}

# 4. Launch NovaBlock - it does the rest (apply_full_block + persistence)
Write-Host "[4] Launching NovaBlock..." -ForegroundColor Cyan
try {
    Start-Process -FilePath $exePath -ErrorAction Stop
    Write-Host "    OK - NovaBlock launched" -ForegroundColor Green
} catch {
    Write-Host "    FAIL - $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 5. Wait for heartbeat to confirm it's actually ticking
Write-Host "[5] Waiting up to 30s for heartbeat..." -ForegroundColor Cyan
$heartbeat = "$env:PROGRAMDATA\NovaBlock\watchdog.heartbeat"
$waited = 0
while ($waited -lt 30) {
    Start-Sleep -Seconds 3
    $waited += 3
    if (Test-Path $heartbeat) {
        $ts = [int](Get-Content $heartbeat -ErrorAction SilentlyContinue)
        $age = [int]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) - $ts
        if ($age -lt 60) {
            Write-Host "    OK - heartbeat fresh ($age s old)" -ForegroundColor Green
            break
        }
    }
}
if ($waited -ge 30) {
    Write-Host "    WARN - no fresh heartbeat after 30s. Scheduled task will retry in <1min." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "NovaBlock REACTIVATED." -ForegroundColor Green
Write-Host "Hosts/DNS/firewall/policies will be re-applied within ~30s." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Start-Sleep -Seconds 5
