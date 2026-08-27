# ============================================================
# NovaBlock - EMERGENCY RESET
# ============================================================
# Last-resort cleanup. Disables EVERYTHING NovaBlock-related plus
# the Windows Firewall so Chrome and other apps work IMMEDIATELY.
# NovaBlock is left fully OFF. Relaunch NovaBlock.exe (admin) when
# you want protection back.
#
# Designed to be portable: no hardcoded paths, uses %WINDIR% and
# %PROGRAMDATA%, runs on any Windows install with NovaBlock.
#
# Two ways to run:
#   1) Local: double-click EMERGENCY_RESET.bat (auto-elevates)
#   2) Remote one-liner (PowerShell admin):
#      iex (irm https://raw.githubusercontent.com/novaiax/novablock-X/main/EMERGENCY_RESET.ps1)
# ============================================================

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

# Self-elevate check
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "This script needs admin rights." -ForegroundColor Red
    Write-Host "Reopen PowerShell as Administrator and rerun:" -ForegroundColor Yellow
    Write-Host "  iex (irm https://raw.githubusercontent.com/novaiax/novablock-X/main/EMERGENCY_RESET.ps1)" -ForegroundColor Cyan
    exit 1
}

Write-Host "=== EMERGENCY RESET ===" -ForegroundColor Yellow

# 1. Kill NovaBlock
Write-Host "[1] Killing NovaBlock processes + tasks..." -ForegroundColor Cyan
schtasks /End /TN NovaBlockWatchdog 2>$null | Out-Null
schtasks /End /TN NovaBlockApp 2>$null | Out-Null
Stop-Process -Name NovaBlock -Force -ErrorAction SilentlyContinue
Stop-Process -Name "NovaBlock-Dev" -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
Write-Host "    OK" -ForegroundColor Green

# 2. Disable scheduled tasks entirely (prevent auto-restart)
Write-Host "[2] Disabling NovaBlock scheduled tasks..." -ForegroundColor Cyan
schtasks /Change /TN NovaBlockWatchdog /Disable 2>$null | Out-Null
schtasks /Change /TN NovaBlockApp /Disable 2>$null | Out-Null
Write-Host "    OK" -ForegroundColor Green

# 3. Mass-wipe firewall rules via COM
Write-Host "[3] Wiping NovaBlock firewall rules (fast COM)..." -ForegroundColor Cyan
try {
    $fw = New-Object -ComObject HNetCfg.FwPolicy2
    $toDelete = @($fw.Rules | Where-Object { $_.Name -like 'NovaBlock_DoH_*' })
    $count = $toDelete.Count
    foreach ($r in $toDelete) { try { $fw.Rules.Remove($r.Name) } catch {} }
    Write-Host "    Wiped $count rules" -ForegroundColor Green
} catch {
    Write-Host "    COM wipe failed: $($_.Exception.Message)" -ForegroundColor Yellow
}

# 4. DISABLE Windows Firewall entirely (TEMPORARY)
Write-Host "[4] Disabling Windows Firewall (TEMPORARY)..." -ForegroundColor Cyan
netsh advfirewall set allprofiles state off | Out-Null
Write-Host "    OK - firewall OFF" -ForegroundColor Green

# 5. Reset DNS to DHCP everywhere
Write-Host "[5] Resetting DNS to DHCP on all active interfaces..." -ForegroundColor Cyan
$adapters = @(Get-NetAdapter | Where-Object { $_.Status -eq 'Up' })
foreach ($a in $adapters) {
    try {
        Set-DnsClientServerAddress -InterfaceAlias $a.Name -ResetServerAddresses -ErrorAction Stop
        Write-Host "    OK - $($a.Name)" -ForegroundColor Green
    } catch {
        Write-Host "    FAIL - $($a.Name): $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# 6. Flush DNS + ARP
Write-Host "[6] Flushing DNS + ARP..." -ForegroundColor Cyan
ipconfig /flushdns | Out-Null
Clear-DnsClientCache -ErrorAction SilentlyContinue
arp -d '*' 2>$null | Out-Null
Write-Host "    OK" -ForegroundColor Green

# 7. Clean hosts file of ALL NovaBlock + YouTube Restricted entries
Write-Host "[7] Cleaning hosts file..." -ForegroundColor Cyan
$hosts = "$env:windir\System32\drivers\etc\hosts"
takeown /f $hosts /a 2>&1 | Out-Null
icacls $hosts /grant 'Administrators:F' 2>&1 | Out-Null
try {
    $content = Get-Content $hosts -ErrorAction Stop
    Copy-Item $hosts "$hosts.bak" -Force
    # Remove everything between NovaBlock markers + the YouTube Restricted line
    $cleaned = New-Object System.Collections.ArrayList
    $inBlock = $false
    foreach ($line in $content) {
        if ($line -match '=== NOVABLOCK START ===') { $inBlock = $true; continue }
        if ($line -match '=== NOVABLOCK END ===')   { $inBlock = $false; continue }
        if ($inBlock) { continue }
        if ($line -match '216\.239\.38\.119') { continue }
        [void]$cleaned.Add($line)
    }
    $cleaned | Set-Content $hosts -Encoding ASCII
    Write-Host "    OK - NovaBlock block + YouTube Restricted removed from hosts" -ForegroundColor Green
} catch {
    Write-Host "    FAIL: $($_.Exception.Message)" -ForegroundColor Yellow
}

# 8. Remove ALL NovaBlock browser policies
Write-Host "[8] Removing browser policies..." -ForegroundColor Cyan
$vendors = @(
    'HKLM:\SOFTWARE\Policies\Google\Chrome',
    'HKLM:\SOFTWARE\Policies\Microsoft\Edge',
    'HKLM:\SOFTWARE\Policies\BraveSoftware\Brave',
    'HKLM:\SOFTWARE\Policies\Opera Software\Opera Stable',
    'HKLM:\SOFTWARE\Policies\Mozilla\Firefox'
)
$policyValues = @('ForceYouTubeRestrict','ForceGoogleSafeSearch','DnsOverHttpsMode','BuiltInDnsClientEnabled','IncognitoModeAvailability','InPrivateModeAvailability','ForceBingSafeSearch','DisablePrivateBrowsing')
foreach ($v in $vendors) {
    foreach ($val in $policyValues) {
        try { Remove-ItemProperty -Path $v -Name $val -ErrorAction Stop } catch {}
    }
    # Firefox DoH path is nested
    try { Remove-ItemProperty -Path "$v\DNSOverHTTPS" -Name 'Enabled' -ErrorAction Stop } catch {}
    try { Remove-ItemProperty -Path "$v\DNSOverHTTPS" -Name 'Locked'  -ErrorAction Stop } catch {}
    # Reddit URLBlocklist subkey - wipe NovaBlock's numeric entries
    $sub = "$v\URLBlocklist"
    try {
        if (Test-Path $sub) {
            Get-Item $sub | ForEach-Object {
                $_.GetValueNames() | Where-Object { $_ -match '^\d+$' } |
                    ForEach-Object { Remove-ItemProperty -Path $sub -Name $_ -ErrorAction SilentlyContinue }
            }
        }
    } catch {}
}
Write-Host "    OK - browser policies cleared (including Reddit URLBlocklist)" -ForegroundColor Green

# 9. Kill all browsers so they restart fresh
Write-Host "[9] Killing browsers (they will need to be reopened)..." -ForegroundColor Cyan
foreach ($p in @('chrome','msedge','brave','firefox','opera','vivaldi')) {
    Stop-Process -Name $p -Force -ErrorAction SilentlyContinue
}
Write-Host "    OK" -ForegroundColor Green

# 10. Verify connectivity
Write-Host "[10] Verifying connectivity..." -ForegroundColor Cyan
$pIP   = Test-Connection 8.8.8.8    -Count 1 -Quiet -ErrorAction SilentlyContinue
$pName = Test-Connection google.com -Count 1 -Quiet -ErrorAction SilentlyContinue
if ($pIP -and $pName) {
    Write-Host "    OK - internet alive (IP + DNS)" -ForegroundColor Green
} elseif ($pIP) {
    Write-Host "    PARTIAL - IP works, DNS resolution fails" -ForegroundColor Yellow
} else {
    Write-Host "    FAIL - no connectivity" -ForegroundColor Red
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "EVERYTHING OFF. Open Chrome - should work now." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "Reactivate later via: NovaBlock.exe (admin) - it will re-arm everything." -ForegroundColor DarkGray
Write-Host ""
Start-Sleep -Seconds 10
