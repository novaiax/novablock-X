@echo off
REM ============================================================
REM NovaBlock - Dev launcher with custom process name
REM ============================================================
REM Runs novablock from source (the Python script) but under a
REM custom process name so Task Manager shows "NovaBlock-Dev.exe"
REM instead of "python.exe" / "pythonw.exe". This avoids killing
REM it by mistake when cleaning up other Python processes.
REM
REM How it works:
REM   1) Locate pythonw.exe (no console window).
REM   2) Copy it next to the original under the name
REM      NovaBlock-Dev.exe (idempotent: skipped if already there
REM      and the source pythonw.exe hasn't changed).
REM   3) Launch novablock via this renamed copy.
REM
REM The copy MUST live in the same folder as pythonw.exe so it
REM finds its DLL siblings (python3xx.dll, vcruntime, etc).
REM
REM Usage: double-click run_dev.bat, or "Run as administrator"
REM if you want NovaBlock to have admin rights from start.
REM ============================================================

setlocal enabledelayedexpansion

cd /d "%~dp0"

REM ----- Find pythonw.exe -----
set "PYW="
for /f "delims=" %%p in ('where pythonw 2^>nul') do (
    if not defined PYW set "PYW=%%p"
)
if "%PYW%"=="" (
    echo [ERROR] pythonw.exe not found in PATH.
    echo Install Python 3.10+ and make sure it's on PATH, then re-run.
    pause
    exit /b 1
)

REM ----- Compute destination path -----
for %%i in ("%PYW%") do set "PY_DIR=%%~dpi"
set "CUSTOM_EXE=%PY_DIR%NovaBlock-Dev.exe"

REM ----- Copy if missing or outdated -----
set "NEED_COPY=0"
if not exist "%CUSTOM_EXE%" set "NEED_COPY=1"
if exist "%CUSTOM_EXE%" (
    for %%a in ("%PYW%") do set "SRC_DATE=%%~ta"
    for %%a in ("%CUSTOM_EXE%") do set "DST_DATE=%%~ta"
    if not "!SRC_DATE!"=="!DST_DATE!" set "NEED_COPY=1"
)
if "%NEED_COPY%"=="1" (
    echo [INFO] Copying pythonw.exe to NovaBlock-Dev.exe...
    copy /Y "%PYW%" "%CUSTOM_EXE%" >nul
    if errorlevel 1 (
        echo [ERROR] Could not copy to %CUSTOM_EXE%.
        echo Try running this script as administrator.
        pause
        exit /b 1
    )
)

REM ----- Launch NovaBlock under the custom name -----
echo [INFO] Launching as NovaBlock-Dev.exe...
start "" "%CUSTOM_EXE%" -m novablock %*
exit /b 0
