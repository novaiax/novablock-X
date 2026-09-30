# NovaBlock v1.0.37 - reparation des sockets et du navigateur
# Garde les protections actives pendant la reparation.

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$problems = 0

function Info($message) { Write-Host "  $message" -ForegroundColor Cyan }
function OK($message) { Write-Host "  [OK] $message" -ForegroundColor Green }
function Issue($message) {
    Write-Host "  [!] $message" -ForegroundColor Yellow
    $script:problems++
}

$admin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host 'Droits administrateur requis. Lance unstick_sockets.bat.' -ForegroundColor Red
    Read-Host 'Entree pour fermer'
    exit 1
}

$dataDir = Join-Path $env:ProgramData 'NovaBlock'
$logDir = if (Test-Path -LiteralPath $dataDir) { $dataDir } else { $env:TEMP }
$logPath = Join-Path $logDir ("unstick-sockets-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
try { Start-Transcript -LiteralPath $logPath -ErrorAction Stop | Out-Null }
catch {
    $logPath = Join-Path $env:TEMP ("unstick-sockets-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    try { Start-Transcript -LiteralPath $logPath -ErrorAction Stop | Out-Null }
    catch {
        Write-Host "Journal impossible a ouvrir : $($_.Exception.Message)" -ForegroundColor Red
        Read-Host 'Entree pour fermer'
        exit 1
    }
}

Write-Host '=== NovaBlock - Reparation des sockets ===' -ForegroundColor Cyan
Info "Journal : $logPath"

$app = $null
try {
    $run = (Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run' `
        -Name NovaBlock -ErrorAction Stop).NovaBlock
    $candidate = $run.Trim('"')
    if (Test-Path -LiteralPath $candidate) { $app = $candidate }
} catch { }
if (-not $app) {
    Issue 'NovaBlock.exe introuvable dans la cle de demarrage.'
}

Write-Host '[1/5] Nettoyage des caches reseau...' -ForegroundColor Cyan
try { Clear-DnsClientCache -ErrorAction Stop; OK 'Cache DNS vide' }
catch { Issue "Cache DNS : $($_.Exception.Message)" }
& ipconfig.exe /flushdns | Out-Null
if ($LASTEXITCODE -ne 0) { Issue 'ipconfig /flushdns a echoue' }

Write-Host '[2/5] Reparation Winsock...' -ForegroundColor Cyan
& netsh.exe winsock reset | Out-Null
if ($LASTEXITCODE -eq 0) { OK 'Winsock repare ; un redemarrage peut etre necessaire' }
else { Issue 'Winsock n a pas pu etre repare' }

Write-Host '[3/5] Reapplication de NovaBlock et des regles DoH...' -ForegroundColor Cyan
if ($app) {
    try {
        $process = Start-Process -FilePath $app -ArgumentList '--repair-firewall' `
            -Wait -PassThru -WindowStyle Hidden -ErrorAction Stop
        if ($process.ExitCode -eq 0) {
            $reportPath = Join-Path $dataDir 'firewall-repair-report.json'
            $report = Get-Content -LiteralPath $reportPath -Raw -ErrorAction Stop | ConvertFrom-Json
            OK ("Regles DoH : {0} -> {1}; doublons retires : {2}" -f `
                $report.before, $report.after, $report.removed)
            if ($report.reboot_required) { Info 'Redemarre Windows pour recharger la politique pare-feu.' }
        } else { Issue 'Reparation des regles DoH non confirmee' }
    } catch { Issue "Regles DoH : $($_.Exception.Message)" }
    try {
        $process = Start-Process -FilePath $app -ArgumentList '--reapply' `
            -Wait -PassThru -ErrorAction Stop
        if ($process.ExitCode -eq 0) { OK 'Protections re-appliquees' }
        else { Issue 'La reapplication des protections a echoue' }
    } catch { Issue "Reapplication : $($_.Exception.Message)" }
}

$recovery = Join-Path $dataDir 'runtime_7c31.exe'
if (Test-Path -LiteralPath $recovery) {
    & $recovery --repair-network | Out-Null
    if ($LASTEXITCODE -eq 0) { OK 'Etat reseau de recuperation coherent' }
    else { Issue 'Etat reseau de recuperation a verifier' }
}

Write-Host '[4/5] Controle du filtrage...' -ForegroundColor Cyan
$family4 = @('1.1.1.3','1.0.0.3','185.228.168.168','185.228.169.168',
             '208.67.222.123','208.67.220.123')
$family6 = @('2606:4700:4700::1113','2606:4700:4700::1003',
             '2a0d:2a00:1::','2a0d:2a00:2::')
$dns = @(Get-DnsClientServerAddress -ErrorAction SilentlyContinue | ForEach-Object { $_.ServerAddresses })
if (@($dns | Where-Object { $_ -in $family4 }).Count -gt 0 -and
    @($dns | Where-Object { $_ -in $family6 }).Count -gt 0) {
    OK 'DNS familiaux IPv4 et IPv6 actifs'
} else { Issue 'DNS familiaux incomplets' }
$rules = @(Get-NetFirewallRule -DisplayName 'NovaBlock_DoH_*' -ErrorAction SilentlyContinue)
$unique = @($rules | Select-Object -ExpandProperty DisplayName -Unique)
if ($rules.Count -eq 78 -and $unique.Count -eq 78) { OK '78 regles DoH distinctes' }
else { Issue "Regles DoH visibles : $($rules.Count), noms distincts : $($unique.Count)" }

Write-Host '[5/5] Controle de connexion...' -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri 'https://example.com' -UseBasicParsing `
        -TimeoutSec 15 -ErrorAction Stop
    if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
        OK 'Connexion HTTPS operationnelle'
    } else { Issue "Reponse HTTPS inattendue : $($response.StatusCode)" }
} catch { Issue "Connexion HTTPS : $($_.Exception.Message)" }

Write-Host "Reparation terminee : $problems point(s) a verifier." -ForegroundColor Cyan
try { Stop-Transcript | Out-Null } catch { }
Read-Host 'Entree pour fermer'
exit [Math]::Min($problems, 1)
