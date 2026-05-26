@echo off
REM ============================================================
REM NovaBlock - REACTIVATE (reverses EMERGENCY_RESET)
REM ============================================================
REM Turns Windows Firewall back ON, re-enables NovaBlock scheduled
REM tasks, and launches NovaBlock.exe which then re-arms hosts,
REM DNS, firewall rules, and browser policies via its in-process
REM watchdog. Mirror image of EMERGENCY_RESET.bat.
REM ============================================================

setlocal

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Re-launching as administrator...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0REACTIVATE.ps1"
exit /b %errorlevel%
