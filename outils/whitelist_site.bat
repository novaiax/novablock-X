@echo off
REM ============================================================
REM NovaBlock - Whitelist site (bypass Cloudflare Family DNS)
REM ============================================================
REM Double-click. UAC popup -> Yes. Asks for the domain to
REM unblock, resolves real IP via Google DNS, writes a hosts
REM entry OUTSIDE the NovaBlock block, force-restarts Dnscache.
REM
REM Use when Cloudflare Family wrongly classifies a legit site
REM as adult. NovaBlock title-monitor still applies for actual
REM porn pages on the unblocked site.
REM ============================================================

setlocal

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0whitelist_site.ps1"
exit /b %errorlevel%
