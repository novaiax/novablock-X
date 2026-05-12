@echo off
REM NovaBlock — One-click updater
REM
REM Stops the running app, rebuilds the exe with the latest code, and relaunches.
REM Your config is preserved (DPAPI-encrypted in C:\ProgramData\NovaBlock).
REM
REM Usage: right-click → "Run as administrator"

setlocal enabledelayedexpansion

echo ============================================================
echo NovaBlock — Update
echo ============================================================
echo.

REM Self-elevate if not admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Re-launching as administrator...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

cd /d "%~dp0"

echo [1/5] Stopping running NovaBlock...
schtasks /End /TN NovaBlockWatchdog >nul 2>&1
taskkill /F /IM NovaBlock.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/5] Unlocking hosts file (in case ACL is blocking rebuild)...
takeown /f C:\Windows\System32\drivers\etc\hosts >nul 2>&1
icacls C:\Windows\System32\drivers\etc\hosts /grant Administrators:F >nul 2>&1

echo [3a/5] Ensuring Python dependencies are installed...
python -m pip install --quiet --upgrade -r requirements.txt pyinstaller
if %errorlevel% neq 0 (
    echo [ERROR] pip install failed. Make sure Python 3.10+ is installed and in PATH.
    pause
    exit /b 1
)

echo [3b/5] Rebuilding NovaBlock.exe...
python -m PyInstaller novablock.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo [4/5] Refreshing scheduled task...
schtasks /Delete /TN NovaBlockWatchdog /F >nul 2>&1

echo [5/5] Launching new version...
start "" "%~dp0dist\NovaBlock.exe"

echo.
echo ============================================================
echo Update done. NovaBlock relaunched. Config preserved.
echo ============================================================
timeout /t 3 /nobreak >nul
exit /b 0
