# ============================================================
# NovaBlock - REACTIVATE v1.0.34
# ============================================================
# Remet en route NovaBlock apres un EMERGENCY_RESET et verifie
# egalement la couche de recuperation v1.0.34.
# ============================================================

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$script:problemes = 0

function OK($m)    { Write-Host "    OK   $m" -ForegroundColor Green }
function Souci($m) { Write-Host "    !!   $m" -ForegroundColor Yellow; $script:problemes++ }
function Info($m)  { Write-Host "         $m" -ForegroundColor DarkGray }

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Droits administrateur requis." -ForegroundColor Red
    Write-Host "Relance REACTIVATE.bat." -ForegroundColor Yellow
    Read-Host "Entree pour fermer"
    exit 1
}

Write-Host ""
Write-Host "=== REACTIVATION DE NOVABLOCK ===" -ForegroundColor Green
$nb = "$env:ProgramData\NovaBlock"

Write-Host "[0] Nettoyage des marqueurs de maintenance..." -ForegroundColor Cyan
foreach ($f in @('shutdown.sentinel','update.lock')) {
    $fp = Join-Path $nb $f
    if (Test-Path $fp) {
        try { Remove-Item $fp -Force -ErrorAction Stop; OK "$f supprime" }
        catch { Souci "$f impossible a supprimer : $($_.Exception.Message)" }
    }
}

Write-Host "[1] Reactivation du pare-feu Windows..." -ForegroundColor Cyan
& netsh advfirewall set allprofiles state on | Out-Null
Start-Sleep -Milliseconds 400
$profils = Get-NetFirewallProfile -ErrorAction SilentlyContinue
$off = @($profils | Where-Object { -not $_.Enabled })
if ($off.Count -eq 0 -and $profils) { OK "pare-feu actif" }
else { Souci "un ou plusieurs profils restent desactives" }

Write-Host "[2] Reactivation des taches NovaBlock..." -ForegroundColor Cyan
foreach ($t in @('NovaBlockWatchdog','NovaBlockApp')) {
    $st = Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    if ($st -and $st.State -eq 'Disabled') {
        try { Enable-ScheduledTask -TaskName $t -ErrorAction Stop | Out-Null } catch { }
        $st = Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    }
    if ($st -and $st.State -ne 'Disabled') { OK "$t actif" }
    else { Info "$t sera recreee par NovaBlock si necessaire" }
}

Write-Host "[3] Recherche et lancement du coeur..." -ForegroundColor Cyan
$exePath = $null
try {
    $v = (Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run' -Name NovaBlock -ErrorAction Stop).NovaBlock
    $c = $v.Trim('"')
    if (Test-Path $c) { $exePath = $c }
} catch { }
if (-not $exePath) {
    foreach ($c in @(
        "$env:LOCALAPPDATA\NovaBlock\NovaBlock.exe",
        "$env:PROGRAMFILES\NovaBlock\NovaBlock.exe",
        "${env:PROGRAMFILES(X86)}\NovaBlock\NovaBlock.exe",
        "D:\code\app\bloqueur distractions\dist\NovaBlock.exe")) {
        if ($c -and (Test-Path $c)) { $exePath = $c; break }
    }
}
if (-not $exePath) {
    Souci "NovaBlock.exe introuvable"
    Read-Host "Entree pour fermer"
    exit 1
}
try { Start-Process -FilePath $exePath -ErrorAction Stop; OK "lancement demande" }
catch { Souci "lancement impossible : $($_.Exception.Message)" }

Write-Host "[4] Attente du heartbeat principal..." -ForegroundColor Cyan
$hb = Join-Path $nb 'watchdog.heartbeat'
$frais = $false
for ($w = 0; $w -lt 36; $w += 2) {
    Start-Sleep -Seconds 2
    if (Test-Path $hb) {
        $ts = 0L
        [long]::TryParse((Get-Content $hb -ErrorAction SilentlyContinue), [ref]$ts) | Out-Null
        $age = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $ts
        if ($age -ge 0 -and $age -lt 60) { OK "coeur actif"; $frais = $true; break }
    }
}
if (-not $frais) { Souci "heartbeat principal non confirme" }

Write-Host "[5] Reparation de la recuperation v1.0.34..." -ForegroundColor Cyan
$recoveryTool = $null
$localTool = Join-Path $PSScriptRoot 'update.exe'
$installedTool = Join-Path $nb 'runtime_7c31.exe'
if (Test-Path $localTool) { $recoveryTool = $localTool }
elseif (Test-Path $installedTool) { $recoveryTool = $installedTool }

if ($recoveryTool) {
    & $recoveryTool --repair | Out-Null
    if ($LASTEXITCODE -eq 0) {
        & $recoveryTool --status | Out-Null
        if ($LASTEXITCODE -eq 0) { OK "mecanisme de recuperation sain" }
        else { Souci "controle de sante de la recuperation echoue" }
    } else { Souci "reparation de la recuperation echouee" }
} else {
    Souci "outil v1.0.34 absent; relance update.bat depuis la derniere release"
}

Write-Host "[6] Verification reseau et protections..." -ForegroundColor Cyan
$dns = (Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.ServerAddresses.Count -gt 0 } |
        Select-Object -First 1 -ExpandProperty ServerAddresses) -join ', '
if ($dns -match '1\.1\.1\.3|1\.0\.0\.3|9\.9\.9\.11') { OK "DNS familial actif" }
else { Info "DNS familial pas encore detecte; NovaBlock peut encore etre en cours de reapplication" }

try {
    $fw = New-Object -ComObject HNetCfg.FwPolicy2
    $n = $fw.Rules.Count
    if ($n -gt 5000) { Souci "$n regles pare-feu; lance REPARE_INTERNET.ps1" }
    else { OK "volume de regles pare-feu coherent" }
} catch { Info "comptage des regles indisponible" }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
if ($script:problemes -eq 0) {
    Write-Host "NOVABLOCK REACTIVE ET VERIFIE." -ForegroundColor Green
} else {
    Write-Host "$($script:problemes) point(s) a verifier ci-dessus." -ForegroundColor Yellow
}
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Read-Host "Entree pour fermer"
