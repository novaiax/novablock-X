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
echo NovaBlock - Update from GitHub
echo ============================================================
echo.

REM ---- Step 1: locate the installed NovaBlock.exe ---------------
echo [1/5] Locating current NovaBlock installation...
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

REM ---- Step 2: stop the running app -----------------------------
echo [2/5] Stopping NovaBlock...
schtasks /End /TN NovaBlockWatchdog >nul 2>&1
schtasks /End /TN NovaBlockApp >nul 2>&1
taskkill /F /IM NovaBlock.exe >nul 2>&1
timeout /t 2 /nobreak >nul

REM Ensure hosts is writable (in case previous install locked the ACL)
echo [3/5] Unlocking hosts file ACL...
takeown /f C:\Windows\System32\drivers\etc\hosts >nul 2>&1
icacls C:\Windows\System32\drivers\etc\hosts /grant Administrators:F >nul 2>&1

REM ---- Step 4: download the latest release ----------------------
echo [4/5] Downloading latest NovaBlock.exe from GitHub...
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
    pause
    exit /b 1
)

REM Sanity check: file must exist and be at least 5 MB
for %%A in ("%TMP_FILE%") do set "DL_SIZE=%%~zA"
if not defined DL_SIZE (
    echo   [ERROR] Downloaded file missing.
    pause
    exit /b 1
)
if %DL_SIZE% lss 5000000 (
    echo   [ERROR] Downloaded file too small (%DL_SIZE% bytes). Probably HTML error page.
    del "%TMP_FILE%" >nul 2>&1
    pause
    exit /b 1
)
echo   Downloaded %DL_SIZE% bytes OK.

REM ---- Step 5: install + relaunch ------------------------------
echo [5/5] Installing new version and re-launching...
REM Make sure install dir exists
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%" >nul 2>&1

move /Y "%TMP_FILE%" "%INSTALL_PATH%" >nul
if %errorlevel% neq 0 (
    echo   [ERROR] Could not replace %INSTALL_PATH%. Is the file locked?
    pause
    exit /b 1
)

REM Remove the old scheduled task — the new exe will re-create it
REM with up-to-date paths at first launch.
schtasks /Delete /TN NovaBlockWatchdog /F >nul 2>&1
schtasks /Delete /TN NovaBlockApp /F >nul 2>&1

REM Launch the new version
start "" "%INSTALL_PATH%"

echo.
echo ============================================================
echo Update complete. NovaBlock re-launched.
echo Your config (encrypted in C:\ProgramData\NovaBlock) is preserved.
echo ============================================================
timeout /t 3 /nobreak >nul
exit /b 0
