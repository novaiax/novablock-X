@echo off
REM ============================================================
REM NovaBlock v1.0.35 - reparation des sockets (lanceur)
REM ============================================================
REM Demande l'UAC puis lance la reparation visible, avec journal conserve.
REM Le script re-applique les protections et verifie DNS, DoH et HTTPS.
REM
REM Usage:
REM   - Double-click            -> auto-elevates via UAC
REM   - Right-click > Run as admin  -> utilise une session deja elevee
REM ============================================================

setlocal

REM Self-elevate if not admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Re-launching as administrator...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

REM Call the PowerShell worker. -ExecutionPolicy Bypass so the
REM user doesn't need to have changed their system-wide policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0unstick_sockets.ps1"
exit /b %errorlevel%
