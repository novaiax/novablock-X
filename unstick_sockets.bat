@echo off
REM ============================================================
REM NovaBlock - Unstick sockets / DNS
REM ============================================================
REM Use this when:
REM   - Internet is slow or some apps can't connect after streaming
REM   - DNS resolution stalls (Google search takes forever)
REM   - You see `cmd timeout` warnings in NovaBlock's log
REM
REM What it does (all reversible, no reboot needed):
REM   1. Restarts the Windows DNS Client service (Dnscache) - frees the
REM      resolver's internal queues
REM   2. Flushes the DNS cache
REM   3. Clears the ARP cache
REM   4. Re-applies Cloudflare Family DNS on every active interface
REM      (defensive: in case a previous netsh timeout left it empty)
REM
REM Usage: right-click -> Run as administrator
REM ============================================================

setlocal enabledelayedexpansion

REM Self-elevate if not admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Re-launching as administrator...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

echo ============================================================
echo NovaBlock - Unstick sockets / DNS
echo ============================================================
echo.

echo [1/4] Restarting Windows DNS Client service...
net stop Dnscache /y >nul 2>&1
timeout /t 1 /nobreak >nul
net start Dnscache >nul 2>&1
if !errorlevel! neq 0 (
    echo   [WARN] Dnscache restart returned errorlevel !errorlevel!
) else (
    echo   [OK]
)

echo [2/4] Flushing DNS cache...
ipconfig /flushdns >nul
if !errorlevel! equ 0 (echo   [OK]) else (echo   [WARN] flushdns errorlevel !errorlevel!)

echo [3/4] Clearing ARP cache...
arp -d * >nul 2>&1
echo   [OK]

echo [4/4] Re-applying Cloudflare Family DNS on active interfaces...
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-NetAdapter ^| Where-Object {$_.Status -eq 'Up'} ^| Select-Object -ExpandProperty Name"') do (
    echo   - Interface: %%i
    netsh interface ipv4 set dns name="%%i" static 1.1.1.3 primary >nul
    netsh interface ipv4 add dns name="%%i" 1.0.0.3 index=2 >nul
    netsh interface ipv6 set dns name="%%i" static 2606:4700:4700::1113 primary >nul
    netsh interface ipv6 add dns name="%%i" 2606:4700:4700::1003 index=2 >nul
)
echo   [OK]

echo.
echo ============================================================
echo Done. Sockets and DNS unstuck.
echo If apps are still disconnected, close them and reopen.
echo ============================================================
timeout /t 3 /nobreak >nul
exit /b 0
