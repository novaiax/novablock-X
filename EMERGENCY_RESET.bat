@echo off
REM ============================================================
REM NovaBlock - EMERGENCY RESET (lanceur)
REM ============================================================
REM Ouvre l'interface securisee. Le reset ne demarre QUE apres avoir
REM retape a la main un code aleatoire de 30 caracteres, copier-coller
REM desactive. La logique du reset est embarquee dans le .ps1, inchangee.
REM
REM Usage : double-clic (il s'eleve tout seul)
REM ============================================================

setlocal

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Relancement en tant qu'administrateur...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

REM -WindowStyle Hidden : pas de console noire derriere la fenetre graphique
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0EMERGENCY_RESET.ps1"
exit /b %errorlevel%
