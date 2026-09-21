@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM NovaBlock - update complet depuis la derniere release GitHub
REM v1.0.34 : coeur + couche de recuperation + verification SHA256
REM ============================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Relance en administrateur...
    if /I "%~1"=="--local" (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0elevate_update.ps1" -ScriptPath "%~f0" -LocalApp "%~f2" -LocalRecovery "%~f3"
    ) else (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0elevate_update.ps1" -ScriptPath "%~f0"
    )
    exit /b !errorlevel!
)

echo ============================================================
echo NovaBlock - Mise a jour depuis GitHub
echo ============================================================
echo.

set "LOCK_DIR=%PROGRAMDATA%\NovaBlock"
set "LOCK_FILE=%LOCK_DIR%\update.lock"
set "SENTINEL=%LOCK_DIR%\shutdown.sentinel"
set "STALE_AFTER=1800"
set "BASE_URL=https://github.com/novaiax/novablock-X/releases/latest/download"
set "RECOVERY_TMP=%TEMP%\NovaBlock-update-v134.exe"
set "SUMS_TMP=%TEMP%\NovaBlock-SHA256SUMS.txt"
set "LOCAL_MODE=0"
set "CORE_SWAPPED=0"

if not exist "%LOCK_DIR%" mkdir "%LOCK_DIR%" >nul 2>&1
>> "%LOCK_DIR%\update-launch.log" echo [%date% %time%] start mode=%~1 app=%~2 recovery=%~3
if /I "%~1"=="--local" (
    if "%~2"=="" goto :local_usage
    if "%~3"=="" goto :local_usage
    set "LOCAL_MODE=1"
    set "LOCAL_APP=%~f2"
    set "LOCAL_RECOVERY=%~f3"
)

if exist "%LOCK_FILE%" (
    set "LOCKTS="
    set /p LOCKTS=<"%LOCK_FILE%"
    for /f %%n in ('powershell -NoProfile -Command "[int]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"') do set NOWTS=%%n
    set /a LOCK_AGE=NOWTS-LOCKTS 2>nul
    if !LOCK_AGE! lss 0 set LOCK_AGE=0
    if !LOCK_AGE! lss %STALE_AFTER% (
        echo [ERROR] Une autre mise a jour semble deja active ^(!LOCK_AGE! s^).
        echo Lance REPARE_INTERNET.ps1 si une ancienne mise a jour s'est interrompue.
        pause
        exit /b 1
    )
    echo [INFO] Ancien verrou de mise a jour detecte, remplacement.
)
for /f %%n in ('powershell -NoProfile -Command "[int]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"') do set ACQUIRE_TS=%%n
> "%LOCK_FILE%" echo !ACQUIRE_TS!

REM ----- 1. Localiser l'installation -----
echo [1/8] Localisation de NovaBlock.exe...
set "INSTALL_PATH="
for /f "tokens=2,*" %%a in ('reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v NovaBlock 2^>nul ^| findstr /R "NovaBlock"') do set "INSTALL_PATH=%%b"
set "INSTALL_PATH=%INSTALL_PATH:"=%"
if "%INSTALL_PATH%"=="" (
    set "INSTALL_PATH=%~dp0..\dist\NovaBlock.exe"
    echo   [WARN] Chemin registre absent, fallback local utilise.
)
for %%i in ("%INSTALL_PATH%") do set "INSTALL_DIR=%%~dpi"
set "TMP_FILE=%INSTALL_PATH%.tmp"
echo   %INSTALL_PATH%

REM ----- 2. Preparer tous les artefacts avant d'arreter l'app -----
echo [2/8] Preparation des artefacts...
del /F /Q "%TMP_FILE%" "%RECOVERY_TMP%" "%SUMS_TMP%" >nul 2>&1
if "%LOCAL_MODE%"=="1" (
    if not exist "%LOCAL_APP%" goto :local_missing
    if not exist "%LOCAL_RECOVERY%" goto :local_missing
    copy /Y "%LOCAL_APP%" "%TMP_FILE%" >nul || goto :local_missing
    copy /Y "%LOCAL_RECOVERY%" "%RECOVERY_TMP%" >nul || goto :local_missing
    powershell -NoProfile -Command "$a=(Get-FileHash '%TMP_FILE%' -Algorithm SHA256).Hash.ToLower(); $r=(Get-FileHash '%RECOVERY_TMP%' -Algorithm SHA256).Hash.ToLower(); [string[]]$lines=@(($a+'  NovaBlock.exe'),($r+'  update.exe')); [IO.File]::WriteAllLines('%SUMS_TMP%',$lines,[Text.Encoding]::ASCII)"
    if errorlevel 1 goto :local_missing
    echo   [OK] Artefacts locaux copies et manifeste SHA-256 genere.
) else (
    call :download "%BASE_URL%/NovaBlock.exe" "%TMP_FILE%"
    if errorlevel 1 goto :download_failed
    call :download "%BASE_URL%/update.exe" "%RECOVERY_TMP%"
    if errorlevel 1 goto :download_failed
    call :download "%BASE_URL%/SHA256SUMS.txt" "%SUMS_TMP%"
    if errorlevel 1 goto :download_failed
)
for %%A in ("%TMP_FILE%") do set "APP_SIZE=%%~zA"
for %%A in ("%RECOVERY_TMP%") do set "REC_SIZE=%%~zA"
if not defined APP_SIZE goto :download_failed
if not defined REC_SIZE goto :download_failed
if !APP_SIZE! lss 5000000 goto :download_failed
if !REC_SIZE! lss 500000 goto :download_failed
echo   [OK] NovaBlock.exe !APP_SIZE! octets, update.exe !REC_SIZE! octets.

REM ----- 3. Verifier SHA256 -----
echo [3/8] Verification SHA-256...
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop'; $m=@{}; foreach($line in (Get-Content '%SUMS_TMP%')){ if($line -match '^([0-9a-fA-F]{64})\s+(.+)$'){ $m[$matches[2].Trim()]=$matches[1].ToLower() } }; if(-not $m.ContainsKey('NovaBlock.exe') -or -not $m.ContainsKey('update.exe')){ throw 'checksums manquants' }; $a=(Get-FileHash '%TMP_FILE%' -Algorithm SHA256).Hash.ToLower(); $r=(Get-FileHash '%RECOVERY_TMP%' -Algorithm SHA256).Hash.ToLower(); if($a -ne $m['NovaBlock.exe']){ throw 'SHA NovaBlock.exe incorrect' }; if($r -ne $m['update.exe']){ throw 'SHA update.exe incorrect' }"
if errorlevel 1 (
    echo   [ERROR] Verification SHA-256 echouee.
    goto :cleanup_fail
)
echo   [OK] Empreintes valides.

REM ----- 4. Arret propre du coeur -----
echo [4/8] Mise en maintenance et attente de l'arret volontaire...
> "%SENTINEL%" echo update.bat
set /a STOP_WAITED=0
:wait_process_exit
tasklist /FI "IMAGENAME eq NovaBlock.exe" /NH 2>nul | find /I "NovaBlock.exe" >nul
if errorlevel 1 goto :processes_gone
timeout /t 1 /nobreak >nul
set /a STOP_WAITED+=1
if !STOP_WAITED! lss 45 goto :wait_process_exit

:process_still_running
echo   [ERROR] NovaBlock.exe reste actif apres !STOP_WAITED! secondes.
goto :cleanup_fail

:processes_gone
echo   [OK] Tous les composants NovaBlock se sont arretes volontairement.

REM ----- 5. Remplacer le coeur avec sauvegarde locale -----
echo [5/8] Installation transactionnelle du coeur...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%" >nul 2>&1
set "PREVIOUS_FILE=%INSTALL_PATH%.previous"
if exist "%INSTALL_PATH%" (
    copy /Y "%INSTALL_PATH%" "%PREVIOUS_FILE%" >nul 2>&1
    if errorlevel 1 (
        echo   [ERROR] Impossible de sauvegarder le coeur actuel.
        goto :cleanup_fail
    )
)
set /a MOVE_TRY=0
:retry_move
set /a MOVE_TRY+=1
move /Y "%TMP_FILE%" "%INSTALL_PATH%" >nul 2>&1
if !errorlevel! equ 0 goto :move_ok
if !MOVE_TRY! lss 12 (
    echo   Fichier encore occupe, essai !MOVE_TRY!/12...
    timeout /t 1 /nobreak >nul
    goto :retry_move
)
echo   [ERROR] Impossible de remplacer %INSTALL_PATH%.
goto :cleanup_fail

:move_ok
set "CORE_SWAPPED=1"
echo   [OK] Coeur installe.

REM ----- 6. Installer/reparer la couche v1.0.34 -----
echo [6/8] Installation/reparation de la recuperation v1.0.34...
"%RECOVERY_TMP%" --repair
if errorlevel 1 (
    echo   [ERROR] La couche de recuperation n'a pas passe son controle de sante.
    goto :cleanup_fail
)
echo   [OK] Recuperation v1.0.34 active.

REM ----- 7. Relancer le coeur dans la session interactive -----
echo [7/8] Relance interactive de NovaBlock...
del "%SENTINEL%" >nul 2>&1
schtasks /Run /TN NovaBlockApp >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] La tache interactive NovaBlockApp n'a pas pu etre lancee.
    goto :cleanup_fail
)
set "HEARTBEAT=%LOCK_DIR%\watchdog.heartbeat"
set /a WAITED=0
:wait_heartbeat
timeout /t 2 /nobreak >nul
set /a WAITED+=2
for /f %%h in ('powershell -NoProfile -Command "$h=Get-Content '%HEARTBEAT%' -ErrorAction SilentlyContinue; if($h){[int64]$h}else{0}"') do set HEART_TS=%%h
for /f %%n in ('powershell -NoProfile -Command "[int64]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"') do set NOWTS=%%n
set /a HEART_AGE=NOWTS-HEART_TS 2>nul
if defined HEART_TS if !HEART_AGE! leq 60 goto :heartbeat_ok
if !WAITED! lss 36 goto :wait_heartbeat
echo   [WARN] Heartbeat principal pas encore frais. Les couches de recuperation continueront a reessayer.
goto :post_start

:heartbeat_ok
echo   [OK] Coeur vivant ^(heartbeat !HEART_AGE! s^).

:post_start
del "%LOCK_FILE%" >nul 2>&1
timeout /t 1 /nobreak >nul
"%RECOVERY_TMP%" --status >nul 2>&1
if errorlevel 1 (
    echo   [WARN] Verification finale de la recuperation non concluante, tentative de reparation...
    "%RECOVERY_TMP%" --repair >nul 2>&1
)

REM ----- 8. Sante finale : filtre familial + Internet utile -----
echo [8/8] Controle final...
set /a HEALTH=0
set /a DNS_WAITED=0
:wait_family_dns
for /f %%d in ('powershell -NoProfile -Command "$v4=@('1.1.1.3','1.0.0.3','185.228.168.168','185.228.169.168','208.67.222.123','208.67.220.123'); $v6=@('2606:4700:4700::1113','2606:4700:4700::1003','2a0d:2a00:1::','2a0d:2a00:2::'); $s=(Get-DnsClientServerAddress -ErrorAction SilentlyContinue).ServerAddresses; $h4=$false; $h6=$false; foreach($a in $s){if($v4 -contains $a){$h4=$true}; if($v6 -contains $a){$h6=$true}}; if($h4 -and $h6){0}else{1}"') do set DNS_FAMILY_ERROR=%%d
if "!DNS_FAMILY_ERROR!"=="0" goto :family_dns_ok
if !DNS_WAITED! geq 20 goto :family_dns_failed
timeout /t 2 /nobreak >nul
set /a DNS_WAITED+=2
goto :wait_family_dns

:family_dns_failed
if not "!DNS_FAMILY_ERROR!"=="0" (
    echo   [PROBLEME] Les DNS familiaux IPv4 et IPv6 ne sont pas tous actifs.
    set /a HEALTH+=1
)
goto :family_dns_done

:family_dns_ok
echo   [OK] DNS familiaux IPv4 et IPv6 actifs ^(attente !DNS_WAITED! s^)

:family_dns_done

for /f %%d in ('powershell -NoProfile -Command "$sw=[Diagnostics.Stopwatch]::StartNew(); try{[void][System.Net.Dns]::GetHostAddresses('www.google.com'); $sw.Stop(); [int]$sw.Elapsed.TotalMilliseconds}catch{$sw.Stop(); -1}"') do set DNSMS=%%d
if !DNSMS! lss 0 (
    echo   [PROBLEME] Resolution DNS echouee.
    set /a HEALTH+=1
) else echo   [OK] DNS : !DNSMS! ms

for /f %%h in ('powershell -NoProfile -Command "try{$r=Invoke-WebRequest -Uri 'https://example.com' -UseBasicParsing -TimeoutSec 15; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 400){0}else{1}}catch{1}"') do set HTTPS_ERROR=%%h
if not "!HTTPS_ERROR!"=="0" (
    echo   [PROBLEME] La connexion HTTPS de controle a echoue.
    set /a HEALTH+=1
) else echo   [OK] Connexion Internet HTTPS operationnelle

"%RECOVERY_TMP%" --status >nul 2>&1
if errorlevel 1 (
    echo   [PROBLEME] Recuperation v1.0.34 non saine.
    set /a HEALTH+=1
) else echo   [OK] Recuperation v1.0.34 saine

tasklist /FI "IMAGENAME eq NovaBlock.exe" /NH 2>nul | find /I "NovaBlock.exe" >nul
if errorlevel 1 (
    echo   [WARN] Processus principal pas encore visible.
) else echo   [OK] NovaBlock est actif

del /F /Q "%RECOVERY_TMP%" "%SUMS_TMP%" >nul 2>&1
echo.
echo ============================================================
if !HEALTH! equ 0 (
    echo Mise a jour terminee et verifiee.
    >> "%LOCK_DIR%\update-launch.log" echo [%date% %time%] complete health=0
    del /F /Q "%PREVIOUS_FILE%" >nul 2>&1
) else (
    echo Mise a jour terminee avec !HEALTH! point^(s^) a verifier.
    >> "%LOCK_DIR%\update-launch.log" echo [%date% %time%] complete health=!HEALTH!
)
echo Configuration conservee dans %PROGRAMDATA%\NovaBlock.
echo ============================================================
timeout /t 3 /nobreak >nul
exit /b !HEALTH!

:download
set "DL_URL=%~1"
set "DL_OUT=%~2"
curl.exe --version >nul 2>&1
if %errorlevel% equ 0 (
    curl.exe -L -f --retry 3 --retry-delay 1 --progress-bar -o "%DL_OUT%" "%DL_URL%"
    exit /b !errorlevel!
)
powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri '%DL_URL%' -OutFile '%DL_OUT%' -UseBasicParsing; exit 0 } catch { exit 1 }"
exit /b !errorlevel!

:download_failed
echo   [ERROR] Telechargement echoue ou fichier invalide.
goto :cleanup_fail

:local_usage
echo Usage : update.bat --local "CHEMIN\NovaBlock.exe" "CHEMIN\update.exe"
exit /b 2

:local_missing
echo   [ERROR] Artefact local absent ou impossible a copier.
goto :cleanup_fail

:cleanup_fail
>> "%LOCK_DIR%\update-launch.log" echo [%date% %time%] failed core_swapped=%CORE_SWAPPED%
if "%CORE_SWAPPED%"=="1" if exist "%PREVIOUS_FILE%" (
    copy /Y "%PREVIOUS_FILE%" "%INSTALL_PATH%" >nul 2>&1
    if not errorlevel 1 echo   [OK] Coeur precedent restaure.
)
del "%LOCK_FILE%" >nul 2>&1
del "%SENTINEL%" >nul 2>&1
schtasks /Run /TN NovaBlockApp >nul 2>&1
schtasks /Run /TN NovaBlockWatchdog >nul 2>&1
if exist "%TMP_FILE%" del /F /Q "%TMP_FILE%" >nul 2>&1
del /F /Q "%RECOVERY_TMP%" "%SUMS_TMP%" >nul 2>&1
echo.
echo ============================================================
echo Mise a jour interrompue proprement. L'installation precedente a ete rearmee.
echo ============================================================
exit /b 1
