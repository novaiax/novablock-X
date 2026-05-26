@echo off
REM ============================================================
REM NovaBlock - EMERGENCY RESET (last-resort wrapper)
REM ============================================================
REM Use this when EVERYTHING is broken: Chrome spins forever, no
REM internet, NovaBlock can't be killed normally, update.bat fails,
REM unstick_sockets.bat takes forever. This is the nuclear option.
REM
REM What it does:
REM   - Kills NovaBlock processes + DISABLES its scheduled tasks
REM   - Wipes ALL NovaBlock_DoH_* firewall rules (fast COM)
REM   - DISABLES Windows Firewall entirely (temporary!)
REM   - Resets DNS to DHCP on every interface
REM   - Flushes DNS + ARP caches
REM   - Empties the NovaBlock block from hosts file
REM   - Removes ALL NovaBlock browser policies (Chrome/Edge/Brave/
REM     Firefox/Opera): DoH, SafeSearch, Incognito, YouTube Restrict
REM   - Kills all browsers so they restart fresh
REM   - Verifies connectivity
REM
REM After running this, NovaBlock is fully OFF and Chrome works.
REM To re-enable NovaBlock later: double-click NovaBlock.exe (admin),
REM it re-arms hosts/DNS/firewall/policies/scheduled-tasks.
REM
REM Usage:
REM   - Double-click       -> auto-elevates via UAC
REM   - Right-click > Run as admin
REM ============================================================

setlocal

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Re-launching as administrator...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0EMERGENCY_RESET.ps1"
exit /b %errorlevel%
