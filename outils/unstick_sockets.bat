@echo off
REM ============================================================
REM NovaBlock - Master Repair Tool (wrapper)
REM ============================================================
REM This .bat exists only to self-elevate and call the powerful
REM PowerShell repair script (unstick_sockets.ps1) next to it.
REM ALL the actual logic lives in the .ps1 — edit there, not here.
REM
REM What it does: fixes every known failure mode of NovaBlock and
REM the browsers in one go — duplicate firewall rules, stuck DNS,
REM legacy YouTube Restricted entries, obsolete browser policies,
REM Chrome cache, Winsock corruption, dead scheduled tasks, etc.
REM
REM Usage:
REM   - Double-click            -> auto-elevates via UAC
REM   - Right-click > Run as admin  -> skips the elevation prompt
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
