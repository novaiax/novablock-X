@echo off
REM ============================================================
REM NovaBlock - Update from GitHub release
REM ============================================================
REM Downloads the latest NovaBlock.exe from
REM https://github.com/novaiax/novablock-X/releases/latest
REM and replaces the running one. No Python required.
REM
REM For local rebuild from source (requires Python + PyInstaller),
REM use update_local.bat instead.
REM
REM Usage: right-click -> Run as administrator
REM
REM ------ Concurrency / safety design ------
REM Yann previously could just close the update cmd window mid-flight
REM and the watchdog would die because update.bat used to /Delete the
REM scheduled tasks before re-creating them. Two fixes:
REM
REM 1) Lock file at C:\ProgramData\NovaBlock\update.lock with a unix
REM    timestamp. A second update.bat refuses to run if the lock is
REM    less than 30 minutes old. If older, it is treated as stale
REM    (previous run crashed/closed) and overwritten.
REM
REM 2) Scheduled tasks are NEVER /Delete'd by this script — only /End
REM    is used to stop the running instance long enough to overwrite
REM    the .exe. The NovaBlockWatchdog task fires every minute under
REM    SYSTEM, so even if this script is killed mid-way the watchdog
REM    automatically re-arms hosts/DNS/firewall at the next tick.
REM
REM If something goes really wrong, run unstick_sockets.bat — it
REM clears stale locks, restarts services, and triggers the watchdog
REM to re-apply everything immediately.
REM ============================================================

setlocal enabledelayedexpansion

REM ----- Self-elevate if not admin -----
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Re-launching as administrator...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

echo ============================================================
echo NovaBlock - Update from GitHub
echo ============================================================
echo.

REM ----- Step 0: acquire update lock -----
set "LOCK_DIR=%PROGRAMDATA%\NovaBlock"
set "LOCK_FILE=%LOCK_DIR%\update.lock"
set "STALE_AFTER=1800"

if exist "%LOCK_FILE%" (
    set "LOCKTS="
    set /p LOCKTS=<"%LOCK_FILE%"
    for /f %%n in ('powershell -NoProfile -Command "[int]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"') do set NOWTS=%%n
    set /a LOCK_AGE=NOWTS-LOCKTS 2>nul
    if !LOCK_AGE! lss 0 set LOCK_AGE=0
    if !LOCK_AGE! lss %STALE_AFTER% (
        echo [ERROR] Another update is already running ^(started !LOCK_AGE!s ago^).
        echo Wait for it to finish, or if you're sure it crashed, delete:
        echo   %LOCK_FILE%
        echo and re-run this script. Lock auto-expires after %STALE_AFTER%s.
        pause
        exit /b 1
    )
    echo [INFO] Stale lock found ^(!LOCK_AGE!s old^), overwriting.
)

if not exist "%LOCK_DIR%" mkdir "%LOCK_DIR%" >nul 2>&1
for /f %%n in ('powershell -NoProfile -Command "[int]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"') do set ACQUIRE_TS=%%n
> "%LOCK_FILE%" echo !ACQUIRE_TS!

REM ----- Step 1: locate the installed NovaBlock.exe -----
echo [1/6] Locating current NovaBlock installation...
set "INSTALL_PATH="
for /f "tokens=2,*" %%a in ('reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v NovaBlock 2^>nul ^| findstr /R "NovaBlock"') do (
    set "INSTALL_PATH=%%b"
)
REM Strip surrounding quotes if present
set "INSTALL_PATH=%INSTALL_PATH:"=%"

if "%INSTALL_PATH%"=="" (
    REM Fallback: assume next to this script in dist\
    set "INSTALL_PATH=%~dp0dist\NovaBlock.exe"
    echo   [WARN] HKLM\Run\NovaBlock not found, using fallback path:
)
echo   Found at: %INSTALL_PATH%

REM Get the install directory (without filename)
for %%i in ("%INSTALL_PATH%") do set "INSTALL_DIR=%%~dpi"

REM ----- Step 2: download to a temp file (NovaBlock still running) -----
echo [2/6] Downloading latest NovaBlock.exe from GitHub...
set "DOWNLOAD_URL=https://github.com/novaiax/novablock-X/releases/latest/download/NovaBlock.exe"
set "TMP_FILE=%INSTALL_PATH%.tmp"

REM Try curl first (built-in on Windows 10 1803+); fall back to PowerShell
curl --version >nul 2>&1
if %errorlevel% equ 0 (
    curl -L -f --progress-bar -o "%TMP_FILE%" "%DOWNLOAD_URL%"
    set "DL_RESULT=!errorlevel!"
) else (
    powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = 'Tls12'; Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%TMP_FILE%' -UseBasicParsing } catch { exit 1 }"
    set "DL_RESULT=!errorlevel!"
)

if not !DL_RESULT! equ 0 (
    echo   [ERROR] Download failed. Check your internet connection.
    if exist "%TMP_FILE%" del "%TMP_FILE%" >nul 2>&1
    goto :cleanup_fail
)

REM Sanity check: file must exist and be at least 5 MB
for %%A in ("%TMP_FILE%") do set "DL_SIZE=%%~zA"
if not defined DL_SIZE (
    echo   [ERROR] Downloaded file missing.
    goto :cleanup_fail
)
if %DL_SIZE% lss 5000000 (
    echo   [ERROR] Downloaded file too small ^(%DL_SIZE% bytes^). Probably HTML error page.
    del "%TMP_FILE%" >nul 2>&1
    goto :cleanup_fail
)
echo   Downloaded %DL_SIZE% bytes OK.

REM ----- Step 3: stop running instance (do NOT delete the tasks!) -----
echo [3/6] Stopping NovaBlock to free the exe ^(scheduled tasks kept^)...
schtasks /End /TN NovaBlockWatchdog >nul 2>&1
schtasks /End /TN NovaBlockApp >nul 2>&1
taskkill /F /IM NovaBlock.exe >nul 2>&1
timeout /t 2 /nobreak >nul

REM ----- Step 4: ensure hosts ACL is writable -----
echo [4/6] Unlocking hosts file ACL...
takeown /f C:\Windows\System32\drivers\etc\hosts >nul 2>&1
icacls C:\Windows\System32\drivers\etc\hosts /grant Administrators:F >nul 2>&1

REM ----- Step 5: swap exe -----
echo [5/6] Installing new version...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%" >nul 2>&1
move /Y "%TMP_FILE%" "%INSTALL_PATH%" >nul
if %errorlevel% neq 0 (
    echo   [ERROR] Could not replace %INSTALL_PATH%. Is the file locked?
    echo   The watchdog scheduled task is still in place — it will restart
    echo   NovaBlock from the OLD exe within 60 seconds. You can re-run
    echo   update.bat after fixing the issue.
    goto :cleanup_fail
)

REM ----- Step 6: relaunch + verify -----
echo [6/6] Re-launching NovaBlock and verifying it comes up...
start "" "%INSTALL_PATH%"

REM Wait up to 30s for the new app to write a fresh heartbeat.
REM The in-process watchdog touches it every 30s.
set "HEARTBEAT=%LOCK_DIR%\watchdog.heartbeat"
set /a WAITED=0
:wait_heartbeat
timeout /t 3 /nobreak >nul
set /a WAITED=WAITED+3
if not exist "%HEARTBEAT%" (
    if !WAITED! lss 30 goto wait_heartbeat
    echo   [WARN] No heartbeat file after !WAITED!s — new exe may not have started.
    echo   The NovaBlockWatchdog scheduled task will retry every minute.
    goto :cleanup_ok
)

for /f %%h in ('powershell -NoProfile -Command "$h=Get-Content '%HEARTBEAT%' -ErrorAction SilentlyContinue; if($h){[int]$h}else{0}"') do set HEART_TS=%%h
for /f %%n in ('powershell -NoProfile -Command "[int]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"') do set NOWTS=%%n
set /a HEART_AGE=NOWTS-HEART_TS
if !HEART_AGE! gtr 60 (
    if !WAITED! lss 30 goto wait_heartbeat
    echo   [WARN] Heartbeat is !HEART_AGE!s old — new app may not be ticking.
) else (
    echo   [OK] New NovaBlock is alive ^(heartbeat !HEART_AGE!s old^).
)

:cleanup_ok
del "%LOCK_FILE%" >nul 2>&1
echo.
echo ============================================================
echo Update complete. NovaBlock re-launched.
echo Your config ^(encrypted in C:\ProgramData\NovaBlock^) is preserved.
echo ============================================================
timeout /t 3 /nobreak >nul
exit /b 0

:cleanup_fail
del "%LOCK_FILE%" >nul 2>&1
echo.
echo ============================================================
echo Update FAILED. NovaBlock's scheduled task is still in place
echo and will keep enforcing the block from the previous .exe.
echo If something seems off, run unstick_sockets.bat as admin.
echo ============================================================
pause
exit /b 1
