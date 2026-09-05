@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM NovaBlock - Update from latest GitHub release
REM Robust against the old exe remaining locked for a few seconds.
REM Usage: right-click -> Run as administrator
REM ============================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Re-launching as administrator...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

echo ============================================================
echo NovaBlock - Update from GitHub
echo ============================================================
echo.

set "LOCK_DIR=%PROGRAMDATA%\NovaBlock"
set "LOCK_FILE=%LOCK_DIR%\update.lock"
set "SENTINEL=%LOCK_DIR%\shutdown.sentinel"
set "STALE_AFTER=1800"

if not exist "%LOCK_DIR%" mkdir "%LOCK_DIR%" >nul 2>&1

if exist "%LOCK_FILE%" (
    set "LOCKTS="
    set /p LOCKTS=<"%LOCK_FILE%"
    for /f %%n in ('powershell -NoProfile -Command "[int]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"') do set NOWTS=%%n
    set /a LOCK_AGE=NOWTS-LOCKTS 2>nul
    if !LOCK_AGE! lss 0 set LOCK_AGE=0
    if !LOCK_AGE! lss %STALE_AFTER% (
        echo [ERROR] Another update is already running ^(started !LOCK_AGE!s ago^).
        echo If the previous update crashed, delete:
        echo   %LOCK_FILE%
        echo then re-run this updater.
        pause
        exit /b 1
    )
    echo [INFO] Stale update lock found; replacing it.
)
for /f %%n in ('powershell -NoProfile -Command "[int]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"') do set ACQUIRE_TS=%%n
> "%LOCK_FILE%" echo !ACQUIRE_TS!

REM ----- Step 1: locate installed exe -----
echo [1/7] Locating current NovaBlock installation...
set "INSTALL_PATH="
for /f "tokens=2,*" %%a in ('reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v NovaBlock 2^>nul ^| findstr /R "NovaBlock"') do set "INSTALL_PATH=%%b"
set "INSTALL_PATH=%INSTALL_PATH:"=%"
if "%INSTALL_PATH%"=="" (
    set "INSTALL_PATH=%~dp0dist\NovaBlock.exe"
    echo   [WARN] Registry path missing, using fallback path.
)
echo   Found at: %INSTALL_PATH%
for %%i in ("%INSTALL_PATH%") do set "INSTALL_DIR=%%~dpi"

REM ----- Step 2: download while old app still runs -----
echo [2/7] Downloading latest NovaBlock.exe from GitHub...
set "DOWNLOAD_URL=https://github.com/novaiax/novablock-X/releases/latest/download/NovaBlock.exe"
set "TMP_FILE=%INSTALL_PATH%.tmp"
if exist "%TMP_FILE%" del /F /Q "%TMP_FILE%" >nul 2>&1

curl --version >nul 2>&1
if %errorlevel% equ 0 (
    curl -L -f --progress-bar -o "%TMP_FILE%" "%DOWNLOAD_URL%"
    set "DL_RESULT=!errorlevel!"
) else (
    powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%TMP_FILE%' -UseBasicParsing } catch { exit 1 }"
    set "DL_RESULT=!errorlevel!"
)
if not !DL_RESULT! equ 0 goto :download_failed
for %%A in ("%TMP_FILE%") do set "DL_SIZE=%%~zA"
if not defined DL_SIZE goto :download_failed
if !DL_SIZE! lss 5000000 goto :download_failed
echo   Downloaded !DL_SIZE! bytes OK.

REM ----- Step 3: stop ALL NovaBlock processes, then VERIFY -----
echo [3/7] Stopping NovaBlock and waiting for file handles to close...
schtasks /End /TN NovaBlockWatchdog >nul 2>&1
schtasks /End /TN NovaBlockApp >nul 2>&1
> "%SENTINEL%" echo update.bat

REM Give main + companion time to observe the sentinel and self-exit.
set /a STOP_WAITED=0
:wait_process_exit
tasklist /FI "IMAGENAME eq NovaBlock.exe" /NH 2>nul | find /I "NovaBlock.exe" >nul
if errorlevel 1 goto :processes_gone

REM Fallback for old versions / a stuck process. This may be denied by the
REM process DACL; the sentinel remains the primary shutdown mechanism.
taskkill /F /T /IM NovaBlock.exe >nul 2>&1
powershell -NoProfile -Command "Get-Process NovaBlock -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue" >nul 2>&1

timeout /t 1 /nobreak >nul
set /a STOP_WAITED+=1
if !STOP_WAITED! lss 35 goto :wait_process_exit

:process_still_running
echo   [ERROR] NovaBlock.exe is still running after !STOP_WAITED! seconds.
echo   Windows is still holding the executable open, so replacing it would fail.
echo   Update aborted safely; the old version will be allowed to restart.
goto :cleanup_fail

:processes_gone
echo   [OK] All NovaBlock.exe processes exited.
REM Windows can retain the image section briefly after process exit.
timeout /t 2 /nobreak >nul

REM ----- Step 4: hosts ACL -----
echo [4/7] Unlocking hosts file ACL...
takeown /f C:\Windows\System32\drivers\etc\hosts >nul 2>&1
icacls C:\Windows\System32\drivers\etc\hosts /grant *S-1-5-32-544:F >nul 2>&1

REM ----- Step 5: replace exe with retries -----
echo [5/7] Installing new version...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%" >nul 2>&1
set /a MOVE_TRY=0
:retry_move
set /a MOVE_TRY+=1
move /Y "%TMP_FILE%" "%INSTALL_PATH%" >nul 2>&1
if !errorlevel! equ 0 goto :move_ok

if !MOVE_TRY! lss 12 (
    echo   File still busy; retry !MOVE_TRY!/12...
    REM Re-check no NovaBlock process came back while the sentinel is active.
    schtasks /End /TN NovaBlockWatchdog >nul 2>&1
    schtasks /End /TN NovaBlockApp >nul 2>&1
    taskkill /F /T /IM NovaBlock.exe >nul 2>&1
    timeout /t 1 /nobreak >nul
    goto :retry_move
)

echo   [ERROR] Could not replace %INSTALL_PATH% after !MOVE_TRY! attempts.
echo   The executable is still locked by Windows or another process.
goto :cleanup_fail

:move_ok
echo   [OK] New executable installed.

REM ----- Step 6: relaunch -----
echo [6/7] Re-launching NovaBlock and verifying startup...
del "%SENTINEL%" >nul 2>&1
start "" "%INSTALL_PATH%"

set "HEARTBEAT=%LOCK_DIR%\watchdog.heartbeat"
set /a WAITED=0
:wait_heartbeat
timeout /t 3 /nobreak >nul
set /a WAITED+=3
for /f %%h in ('powershell -NoProfile -Command "$h=Get-Content '%HEARTBEAT%' -ErrorAction SilentlyContinue; if($h){[int]$h}else{0}"') do set HEART_TS=%%h
for /f %%n in ('powershell -NoProfile -Command "[int]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"') do set NOWTS=%%n
set /a HEART_AGE=NOWTS-HEART_TS 2>nul
if defined HEART_TS if !HEART_AGE! leq 60 goto :heartbeat_ok
if !WAITED! lss 36 goto :wait_heartbeat
echo   [WARN] Fresh heartbeat not seen yet. Scheduled recovery will retry if needed.
goto :cleanup_ok

:heartbeat_ok
echo   [OK] NovaBlock is alive ^(heartbeat !HEART_AGE!s old^).

:cleanup_ok
del "%LOCK_FILE%" >nul 2>&1

echo.
echo [7/7] Quick health check...
set /a HEALTH=0
for /f %%d in ('powershell -NoProfile -Command "$sw=[Diagnostics.Stopwatch]::StartNew(); try{[System.Net.Dns]::GetHostAddresses('www.google.com')^|Out-Null; $sw.Stop(); [int]$sw.Elapsed.TotalMilliseconds}catch{$sw.Stop(); -1}"') do set DNSMS=%%d
if !DNSMS! lss 0 (
    echo   [PROBLEM] DNS resolution failed.
    set /a HEALTH+=1
) else (
    echo   [OK] DNS resolution: !DNSMS! ms
)
schtasks /Query /TN NovaBlockWatchdog >nul 2>&1
if errorlevel 1 (
    echo   [PROBLEM] NovaBlockWatchdog task missing.
    set /a HEALTH+=1
) else echo   [OK] Scheduled watchdog present

tasklist /FI "IMAGENAME eq NovaBlock.exe" /NH 2>nul | find /I "NovaBlock.exe" >nul
if errorlevel 1 (
    echo   [WARN] NovaBlock process not visible yet; watchdog will retry.
) else echo   [OK] NovaBlock is running

echo.
echo ============================================================
echo Update complete. Configuration in C:\ProgramData\NovaBlock was preserved.
echo ============================================================
timeout /t 3 /nobreak >nul
exit /b 0

:download_failed
echo   [ERROR] Download failed or downloaded file is invalid.
if exist "%TMP_FILE%" del /F /Q "%TMP_FILE%" >nul 2>&1
goto :cleanup_fail

:cleanup_fail
del "%LOCK_FILE%" >nul 2>&1
del "%SENTINEL%" >nul 2>&1
REM Re-arm the existing installation after a failed update.
schtasks /Run /TN NovaBlockApp >nul 2>&1
schtasks /Run /TN NovaBlockWatchdog >nul 2>&1
echo.
echo ============================================================
echo Update FAILED safely. The previous NovaBlock installation was re-armed.
echo ============================================================
pause
exit /b 1
