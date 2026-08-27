# ============================================================
# NovaBlock - Master Repair Script
# ============================================================
# Fixes EVERY known failure mode of NovaBlock + Chrome in one go.
# Designed to be force-it-fix-it: every step has try/catch, no step
# blocks another, no Read-Host pause. Use this whenever:
#   - Chrome / browsers can't connect, spin forever, or crash
#   - Internet works (ping IP) but pages don't load
#   - NovaBlock seems stuck or aggressive
#   - Update.bat fails or update sequence interrupted
#   - YouTube/Google blocked unexpectedly
#   - Generic "everything is broken" after long uptime
#
# What it does (each step is independent):
#   1.  Stop NovaBlock processes + scheduled tasks (no code needed -
#       this is emergency mode)
#   2.  Clear stale update.lock and shutdown.sentinel
#   3.  Mass-delete duplicate NovaBlock_DoH_* firewall rules via COM
#       (~100x faster than Remove-NetFirewallRule pipeline)
#   4.  Restart Windows DNS Client (Dnscache) - clears resolver queues
#   5.  Flush DNS + ARP caches
#   6.  Reset every active interface DNS to DHCP (box default)
#   7.  Reset Winsock catalog (clears any tampered LSPs)
#   8.  Strip legacy YouTube Restricted Mode entries from hosts file
#   9.  Remove obsolete ForceYouTubeRestrict browser policies
#   10. Kill Chrome / Edge / Brave / Firefox so they restart fresh
#   11. Re-apply Cloudflare Family DNS on active interfaces (safe DNS)
#   12. Verify scheduled tasks still exist (re-arm by launching app)
#   13. Trigger NovaBlock watchdog to re-create 78 fresh firewall rules
#   14. Connectivity sanity check (ping IP + ping name)
#   15. Final report
# ============================================================

$ErrorActionPreference = 'Continue'  # Never abort the whole script on one error
$ProgressPreference   = 'SilentlyContinue'  # Hide cmdlet progress bars

function Write-Step([string]$num, [string]$msg) {
    Write-Host ""
    Write-Host "[$num] $msg" -ForegroundColor Cyan
}
function Write-OK([string]$msg) { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "    [WARN] $msg" -ForegroundColor Yellow }
function Write-Skip([string]$msg) { Write-Host "    [skip] $msg" -ForegroundColor DarkGray }
function Try-Block([scriptblock]$Action, [string]$Label) {
    try {
        & $Action
        Write-OK $Label
        return $true
    } catch {
        Write-Warn "$Label - $($_.Exception.Message.Trim())"
        return $false
    }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "NovaBlock - Master Repair" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# ----------------------------------------------------------------
# Step 1: stop NovaBlock processes + tasks (no code, emergency mode)
# ----------------------------------------------------------------
Write-Step "1/15" "Stopping NovaBlock processes and scheduled tasks"
$null = schtasks /End /TN NovaBlockWatchdog 2>$null
$null = schtasks /End /TN NovaBlockApp 2>$null
Try-Block { Stop-Process -Name NovaBlock -Force -ErrorAction Stop } "NovaBlock processes killed" | Out-Null
Try-Block { Stop-Process -Name "NovaBlock-Dev" -Force -ErrorAction Stop } "NovaBlock-Dev processes killed" | Out-Null
Start-Sleep -Milliseconds 800

# ----------------------------------------------------------------
# Step 2: clear stale locks
# ----------------------------------------------------------------
Write-Step "2/15" "Clearing stale lock and sentinel files"
$pd = "$env:PROGRAMDATA\NovaBlock"
foreach ($f in @("$pd\update.lock", "$pd\shutdown.sentinel", "$pd\main.pid", "$pd\companion.pid")) {
    if (Test-Path $f) {
        Try-Block { Remove-Item $f -Force -ErrorAction Stop } "Removed $(Split-Path $f -Leaf)" | Out-Null
    }
}

# ----------------------------------------------------------------
# Step 3: mass-delete duplicate NovaBlock_DoH_* firewall rules (FAST via COM)
# ----------------------------------------------------------------
Write-Step "3/15" "Cleaning duplicate NovaBlock firewall rules (fast COM API)"
try {
    $fw = New-Object -ComObject HNetCfg.FwPolicy2
    $allRules = @($fw.Rules)
    $toDelete = @($allRules | Where-Object { $_.Name -like 'NovaBlock_DoH_*' })
    $total = $toDelete.Count
    if ($total -eq 0) {
        Write-OK "No NovaBlock firewall rules present (clean state)"
    } else {
        Write-Host "    Deleting $total rule(s) via COM..." -ForegroundColor DarkGray
        $deleted = 0
        $errors = 0
        foreach ($r in $toDelete) {
            try { $fw.Rules.Remove($r.Name); $deleted++ } catch { $errors++ }
        }
        Write-OK "Deleted $deleted/$total rules ($errors errors)"
    }
} catch {
    Write-Warn "COM cleanup failed, falling back to slower cmdlet - $($_.Exception.Message.Trim())"
    Try-Block {
        Get-NetFirewallRule -DisplayName 'NovaBlock_DoH_*' -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    } "Fallback cmdlet cleanup done" | Out-Null
}

# ----------------------------------------------------------------
# Step 4: restart Windows DNS Client (Dnscache)
# ----------------------------------------------------------------
Write-Step "4/15" "Restarting Windows DNS Client (Dnscache)"
$null = & net stop Dnscache /y 2>$null
Start-Sleep -Milliseconds 500
$null = & net start Dnscache 2>$null
if ((Get-Service Dnscache -ErrorAction SilentlyContinue).Status -eq 'Running') {
    Write-OK "Dnscache running"
} else {
    Write-Warn "Dnscache state unclear (may be in protected mode - OK if cache is flushed below)"
}

# ----------------------------------------------------------------
# Step 5: flush DNS + ARP caches
# ----------------------------------------------------------------
Write-Step "5/15" "Flushing DNS and ARP caches"
$null = & ipconfig /flushdns 2>$null
Try-Block { Clear-DnsClientCache -ErrorAction Stop } "DNS cache cleared" | Out-Null
$null = & arp -d '*' 2>$null
Write-OK "ARP cache cleared"

# ----------------------------------------------------------------
# Step 6: reset DNS on every active interface to DHCP (box default)
# ----------------------------------------------------------------
Write-Step "6/15" "Resetting interface DNS to DHCP (router default)"
$adapters = @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' })
foreach ($a in $adapters) {
    Try-Block {
        Set-DnsClientServerAddress -InterfaceAlias $a.Name -ResetServerAddresses -ErrorAction Stop
    } "DHCP DNS on '$($a.Name)'" | Out-Null
}

# ----------------------------------------------------------------
# Step 7: reset Winsock catalog
# ----------------------------------------------------------------
Write-Step "7/15" "Resetting Winsock catalog (clears tampered LSPs)"
$winsockOut = & netsh winsock reset 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-OK "Winsock reset (full effect after reboot, but ongoing connections refresh)"
} else {
    Write-Warn "Winsock reset returned exit $LASTEXITCODE"
}

# ----------------------------------------------------------------
# Step 8: strip legacy YouTube Restricted Mode hosts entries
# ----------------------------------------------------------------
Write-Step "8/15" "Cleaning legacy YouTube Restricted Mode entries from hosts"
$hosts = "$env:windir\System32\drivers\etc\hosts"
if (Test-Path $hosts) {
    try {
        # Ensure writable
        & takeown /f $hosts /a 2>&1 | Out-Null
        & icacls $hosts /grant 'Administrators:F' 2>&1 | Out-Null
        $content = Get-Content $hosts -ErrorAction Stop
        $before = $content.Count
        $cleaned = $content | Where-Object { $_ -notmatch '216\.239\.38\.119' }
        $removed = $before - $cleaned.Count
        if ($removed -gt 0) {
            Copy-Item $hosts "$hosts.bak" -Force -ErrorAction SilentlyContinue
            $cleaned | Set-Content $hosts -Encoding ASCII -ErrorAction Stop
            Write-OK "Removed $removed legacy YouTube Restricted line(s)"
        } else {
            Write-OK "Hosts file already clean (no legacy YouTube Restricted entries)"
        }
    } catch {
        Write-Warn "Could not modify hosts - $($_.Exception.Message.Trim())"
    }
} else {
    Write-Skip "Hosts file not found"
}

# ----------------------------------------------------------------
# Step 9: remove obsolete browser ForceYouTubeRestrict policies
# ----------------------------------------------------------------
Write-Step "9/15" "Removing obsolete ForceYouTubeRestrict browser policies"
foreach ($vendor in @('Google\Chrome','Microsoft\Edge','BraveSoftware\Brave','Opera Software\Opera Stable')) {
    $path = "HKLM:\SOFTWARE\Policies\$vendor"
    try {
        Remove-ItemProperty -Path $path -Name ForceYouTubeRestrict -ErrorAction Stop
        Write-OK "Cleared from $vendor"
    } catch [System.Management.Automation.PSArgumentException] {
        Write-Skip "$vendor (not set)"
    } catch {
        Write-Skip "$vendor - $($_.Exception.Message.Trim())"
    }
}

# ----------------------------------------------------------------
# Step 10: kill browsers so they restart fresh (clears their DNS cache)
# ----------------------------------------------------------------
Write-Step "10/15" "Killing browsers so they restart with fresh DNS cache"
foreach ($p in @('chrome','msedge','brave','firefox','opera','vivaldi')) {
    $procs = @(Get-Process -Name $p -ErrorAction SilentlyContinue)
    if ($procs.Count -gt 0) {
        Try-Block { Stop-Process -Name $p -Force -ErrorAction Stop } "Killed $($procs.Count) $p process(es)" | Out-Null
    } else {
        Write-Skip "$p not running"
    }
}

# ----------------------------------------------------------------
# Step 11: re-apply Cloudflare Family DNS (safe family-friendly DNS)
# ----------------------------------------------------------------
Write-Step "11/15" "Re-applying Cloudflare Family DNS on active interfaces"
$dns4_primary = "1.1.1.3"; $dns4_secondary = "1.0.0.3"
$dns6_primary = "2606:4700:4700::1113"; $dns6_secondary = "2606:4700:4700::1003"
foreach ($a in $adapters) {
    Try-Block {
        Set-DnsClientServerAddress -InterfaceAlias $a.Name -ServerAddresses @($dns4_primary, $dns4_secondary) -ErrorAction Stop
    } "IPv4 family DNS on '$($a.Name)'" | Out-Null
    Try-Block {
        Set-DnsClientServerAddress -InterfaceAlias $a.Name -ServerAddresses @($dns6_primary, $dns6_secondary) -ErrorAction Stop
    } "IPv6 family DNS on '$($a.Name)'" | Out-Null
}

# ----------------------------------------------------------------
# Step 12: verify scheduled tasks still exist
# ----------------------------------------------------------------
Write-Step "12/15" "Verifying NovaBlock scheduled tasks"
foreach ($task in @('NovaBlockWatchdog','NovaBlockApp')) {
    $null = & schtasks /Query /TN $task 2>$null
    if ($LASTEXITCODE -eq 0) { Write-OK "$task present" }
    else                     { Write-Warn "$task MISSING - relaunch NovaBlock.exe manually to re-create" }
}

# ----------------------------------------------------------------
# Step 13: trigger NovaBlock watchdog to re-create 78 fresh DoH rules
# ----------------------------------------------------------------
Write-Step "13/15" "Triggering watchdog to re-add 78 fresh firewall rules"
$null = & schtasks /Run /TN NovaBlockWatchdog 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-OK "Watchdog triggered - rules will repopulate within ~30s"
} else {
    Write-Warn "Could not trigger watchdog (will fire on next 1-min tick anyway)"
}

# ----------------------------------------------------------------
# Step 14: connectivity sanity check
# ----------------------------------------------------------------
Write-Step "14/15" "Connectivity sanity check"
$pingIP   = Test-Connection -ComputerName 8.8.8.8     -Count 1 -Quiet -ErrorAction SilentlyContinue
$pingName = Test-Connection -ComputerName google.com  -Count 1 -Quiet -ErrorAction SilentlyContinue
if ($pingIP -and $pingName) {
    Write-OK "Internet OK (ping IP + DNS resolution both work)"
} elseif ($pingIP) {
    Write-Warn "Ping IP works but DNS resolution fails - check Cloudflare Family reachability"
} else {
    Write-Warn "No connectivity at all - check physical network / router"
}

# ----------------------------------------------------------------
# Step 15: relaunch NovaBlock (kill-ACL + companion + monitor active again)
# ----------------------------------------------------------------
Write-Step "15/15" "Relaunching NovaBlock main app"
$exePath = $null
foreach ($candidate in @(
    "$env:LOCALAPPDATA\NovaBlock\NovaBlock.exe",
    "$env:PROGRAMFILES\NovaBlock\NovaBlock.exe",
    "${env:PROGRAMFILES(X86)}\NovaBlock\NovaBlock.exe",
    "D:\code\app\bloqueur distractions\dist\NovaBlock.exe",
    "D:\code\app\bloqueur distractions\dist-release\NovaBlock.exe"
)) {
    if ($candidate -and (Test-Path $candidate)) { $exePath = $candidate; break }
}
if (-not $exePath) {
    try {
        $regPath = (Get-ItemProperty -Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run' -Name NovaBlock -ErrorAction Stop).NovaBlock
        $exePath = $regPath.Trim('"')
    } catch { }
}
if ($exePath -and (Test-Path $exePath)) {
    Try-Block { Start-Process -FilePath $exePath -ErrorAction Stop } "NovaBlock launched from $exePath" | Out-Null
} else {
    Write-Warn "Could not locate NovaBlock.exe - won't relaunch (scheduled task will fire it at next 1-min tick)"
}

# ----------------------------------------------------------------
# Final report
# ----------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Repair complete." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "If browsers were killed, reopen them. If a problem persists:"
Write-Host "  - run update.bat (admin) to grab the latest fix"
Write-Host "  - check $pd\novablock.log for the actual error"
Write-Host ""
Start-Sleep -Seconds 5
