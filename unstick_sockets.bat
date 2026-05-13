@echo off
REM ============================================================
REM NovaBlock - Repair Tool (one-click fix-everything)
REM ============================================================
REM Use this when:
REM   - Some apps can't connect (Google won't load) but others
REM     keep working (e.g. an active live stream)
REM   - Internet is slow or DNS resolution stalls
REM   - You see `cmd timeout` warnings in NovaBlock's log
REM   - An update was interrupted (closed the window mid-update,
REM     PC rebooted during update, etc.)
REM   - General "weird network behavior" after long uptime
REM
REM What it fixes (all reversible, no reboot needed):
REM   1. Clears stale update.lock if any (so update.bat can run again)
REM   2. Verifies the NovaBlock scheduled tasks still exist
REM      (a crashed update.bat used to /Delete them — no longer)
REM   3. Cleans up duplicate Windows Firewall rules
REM      (NovaBlock_DoH_* used to accumulate without dedup ->
REM      145k rules slowed every new connection. This wipes them
REM      and the watchdog re-adds 78 fresh ones within 60s.)
REM   4. Restarts the Windows DNS Client service (Dnscache)
REM   5. Flushes the DNS cache + clears the ARP cache
REM   6. Re-applies Cloudflare Family DNS on every active interface
REM   7. Triggers the NovaBlock watchdog so the 78 DoH block rules
REM      are re-applied immediately (no minute-wait)
REM
REM Usage: right-click -> Run as administrator
REM ============================================================

setlocal enabledelayedexpansion

REM ----- Self-elevate if not already admin -----
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Re-launching as administrator...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

echo ============================================================
echo NovaBlock - Repair Tool
echo ============================================================
echo.

REM ============================================================
REM Step 1: Clear stale update lock
REM ============================================================
echo [1/7] Checking for stale update lock...
set "LOCK_FILE=%PROGRAMDATA%\NovaBlock\update.lock"
if exist "%LOCK_FILE%" (
    set "LOCKTS="
    set /p LOCKTS=<"%LOCK_FILE%"
    for /f %%n in ('powershell -NoProfile -Command "[int]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"') do set NOWTS=%%n
    set /a LOCK_AGE=NOWTS-LOCKTS 2>nul
    if !LOCK_AGE! lss 0 set LOCK_AGE=0
    if !LOCK_AGE! lss 1800 (
        echo    [INFO] Recent update lock found ^(!LOCK_AGE!s old^). An update may
        echo           be running. If you're sure it crashed/closed, this script
        echo           will clear it.
    ) else (
        echo    [INFO] Stale lock found ^(!LOCK_AGE!s old^), clearing.
    )
    del "%LOCK_FILE%" >nul 2>&1
    if exist "%LOCK_FILE%" (
        echo    [WARN] Could not delete %LOCK_FILE%
    ) else (
        echo    [OK] Lock cleared.
    )
) else (
    echo    [OK] No update lock present.
)

REM ============================================================
REM Step 2: Verify the watchdog scheduled task still exists
REM ============================================================
echo [2/7] Verifying NovaBlock scheduled tasks...
schtasks /Query /TN "NovaBlockWatchdog" >nul 2>&1
if !errorlevel! equ 0 (
    echo    [OK] NovaBlockWatchdog task present.
) else (
    echo    [CRITICAL] NovaBlockWatchdog task is MISSING.
    echo               Without it, NovaBlock will NOT auto-relaunch on kill.
    echo               Launch NovaBlock.exe manually to re-create the tasks.
)
schtasks /Query /TN "NovaBlockApp" >nul 2>&1
if !errorlevel! equ 0 (
    echo    [OK] NovaBlockApp logon task present.
) else (
    echo    [WARN] NovaBlockApp logon task is missing ^(tray won't autostart
    echo           at next logon^). Launch NovaBlock.exe to re-create it.
)

REM ============================================================
REM Step 3: Clean firewall rule duplicates
REM ============================================================
echo [3/7] Counting NovaBlock firewall rules...
for /f %%c in ('powershell -NoProfile -Command "@(Get-NetFirewallRule -DisplayName 'NovaBlock_DoH_*' -ErrorAction SilentlyContinue).Count"') do set RULECOUNT=%%c
echo    Found !RULECOUNT! rules (normal: 78)

if !RULECOUNT! gtr 100 (
    echo    [INFO] Too many rules - cleaning duplicates...
    echo    [INFO] This may take a minute depending on rule count.
    powershell -NoProfile -Command "Get-NetFirewallRule -DisplayName 'NovaBlock_DoH_*' -ErrorAction SilentlyContinue | Remove-NetFirewallRule"
    echo    [OK] All duplicates wiped. Watchdog will re-add 78 fresh rules.
) else (
    echo    [OK] Rule count is normal, nothing to clean.
)

REM ============================================================
REM Step 4: Restart Windows DNS Client service
REM ============================================================
echo [4/7] Restarting Windows DNS Client service (Dnscache)...
net stop Dnscache /y >nul 2>&1
timeout /t 1 /nobreak >nul
net start Dnscache >nul 2>&1
if !errorlevel! neq 0 (
    echo    [WARN] Dnscache restart returned errorlevel !errorlevel!
) else (
    echo    [OK]
)

REM ============================================================
REM Step 5: Flush DNS + clear ARP
REM ============================================================
echo [5/7] Flushing DNS cache and ARP cache...
ipconfig /flushdns >nul
arp -d * >nul 2>&1
echo    [OK]

REM ============================================================
REM Step 6: Re-apply Cloudflare Family DNS on active interfaces
REM ============================================================
echo [6/7] Re-applying Cloudflare Family DNS on active interfaces...
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-NetAdapter ^| Where-Object {$_.Status -eq 'Up'} ^| Select-Object -ExpandProperty Name"') do (
    echo    - Interface: %%i
    netsh interface ipv4 set dns name="%%i" static 1.1.1.3 primary >nul
    netsh interface ipv4 add dns name="%%i" 1.0.0.3 index=2 >nul
    netsh interface ipv6 set dns name="%%i" static 2606:4700:4700::1113 primary >nul
    netsh interface ipv6 add dns name="%%i" 2606:4700:4700::1003 index=2 >nul
)
echo    [OK]

REM ============================================================
REM Step 7: Trigger NovaBlock watchdog to re-add fresh DoH rules
REM ============================================================
echo [7/7] Triggering NovaBlock watchdog (re-adds 78 fresh firewall rules)...
schtasks /Run /TN "NovaBlockWatchdog" >nul 2>&1
if !errorlevel! equ 0 (
    echo    [OK] Watchdog triggered. Firewall rules will be back within ~10s.
) else (
    echo    [WARN] Could not trigger watchdog task. Rules will be re-added on next minute.
)

echo.
echo ============================================================
echo Done. Internet should be back to normal.
echo If apps are still stuck, close them and reopen.
echo ============================================================
timeout /t 5 /nobreak >nul
exit /b 0
