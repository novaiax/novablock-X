@echo off
REM Build a public-distribution NovaBlock.exe (no embedded credentials).
REM The wizard will ask each user for their own Resend API key.
REM
REM Output: dist-release\NovaBlock.exe
REM Your personal _keys.py is preserved (backed up + restored).

setlocal

cd /d "%~dp0"

REM Backup personal keys
if exist novablock\_keys.py (
    echo [INFO] Backing up your personal _keys.py
    copy /Y novablock\_keys.py novablock\_keys.py.bak >nul
    del novablock\_keys.py
)

REM Build
if exist dist-release rd /s /q dist-release
if exist build rd /s /q build

echo [INFO] Building distributable exe...
python -m PyInstaller novablock.spec --clean --noconfirm --distpath dist-release
if %errorlevel% neq 0 (
    echo [ERROR] Build failed.
    if exist novablock\_keys.py.bak move /Y novablock\_keys.py.bak novablock\_keys.py >nul
    exit /b 1
)

REM Restore personal keys
if exist novablock\_keys.py.bak (
    echo [INFO] Restoring your personal _keys.py
    move /Y novablock\_keys.py.bak novablock\_keys.py >nul
)

echo.
echo ============================================================
echo Release exe ready: %CD%\dist-release\NovaBlock.exe
echo ============================================================
echo This exe has NO embedded credentials. The wizard will ask
echo each user for their own Resend API key + from-email.
echo Safe to upload to GitHub Releases.
echo.
exit /b 0
