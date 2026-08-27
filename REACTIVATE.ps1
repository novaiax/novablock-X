# ============================================================
# NovaBlock - REACTIVATE
# ============================================================
# Reverses EMERGENCY_RESET: turns the Windows Firewall back on,
# re-enables the NovaBlock scheduled tasks, and launches
# NovaBlock.exe, which re-applies hosts, DNS, firewall rules,
# browser policies and persistence through its own watchdog.
#
# Every step is CHECKED. The previous version discarded all
# output and printed "OK" unconditionally, so a total failure
# still looked like a success.
#
# Usage:
#   1) Local : double-click REACTIVATE.bat (auto-elevates)
#   2) Remote: iex (irm https://raw.githubusercontent.com/novaiax/novablock-X/main/REACTIVATE.ps1)
# ============================================================

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$script:problemes = 0

function OK($m)     { Write-Host "    OK   $m" -ForegroundColor Green }
function Souci($m)  { Write-Host "    !!   $m" -ForegroundColor Yellow; $script:problemes++ }
function Info($m)   { Write-Host "         $m" -ForegroundColor DarkGray }

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Droits administrateur requis." -ForegroundColor Red
    Write-Host "Relance REACTIVATE.bat (il s'eleve tout seul)." -ForegroundColor Yellow
    Read-Host "Entree pour fermer"
    exit 1
}

Write-Host ""
Write-Host "=== REACTIVATION DE NOVABLOCK ===" -ForegroundColor Green

# 0. Residus qui empechent NovaBlock de demarrer
Write-Host "[0] Fichiers d'etat residuels..." -ForegroundColor Cyan
$nb = "$env:ProgramData\NovaBlock"
# NovaBlock s'auto-termine au demarrage si ce fichier existe : un update
# interrompu ou un uninstall avorte le laisse derriere lui, et l'app
# redemarre puis disparait aussitot sans rien dire.
foreach ($f in @('shutdown.sentinel','update.lock')) {
    $fp = Join-Path $nb $f
    if (Test-Path $fp) {
        try { Remove-Item $fp -Force -ErrorAction Stop; OK "$f supprime (il bloquait le demarrage)" }
        catch { Souci "$f impossible a supprimer : $($_.Exception.Message)" }
    }
}
if (-not (Test-Path (Join-Path $nb 'shutdown.sentinel'))) { OK "aucun sentinel bloquant" }

# 1. Pare-feu Windows
Write-Host "[1] Reactivation du pare-feu Windows..." -ForegroundColor Cyan
& netsh advfirewall set allprofiles state on | Out-Null
Start-Sleep -Milliseconds 500
$profils = Get-NetFirewallProfile -ErrorAction SilentlyContinue
$off = @($profils | Where-Object { -not $_.Enabled })
if ($off.Count -eq 0 -and $profils) { OK "les 3 profils sont actifs" }
else { Souci "profils encore desactives : $(($off | ForEach-Object { $_.Name }) -join ', ')" }

# 2. Taches planifiees
Write-Host "[2] Reactivation des taches planifiees..." -ForegroundColor Cyan
foreach ($t in @('NovaBlockWatchdog','NovaBlockApp')) {
    $st = Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    if (-not $st) { Souci "$t est ABSENTE - NovaBlock la recreera au lancement"; continue }
    if ($st.State -eq 'Disabled') {
        try { Enable-ScheduledTask -TaskName $t -ErrorAction Stop | Out-Null } catch { }
        $st = Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    }
    if ($st.State -eq 'Disabled') { Souci "$t reste desactivee" } else { OK "$t : $($st.State)" }
}

# 3. Localiser l'exe
Write-Host "[3] Recherche de NovaBlock.exe..." -ForegroundColor Cyan
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
    Souci "NovaBlock.exe INTROUVABLE - installe-le d'abord"
    Read-Host "Entree pour fermer"
    exit 1
}
OK "trouve : $exePath"

# 4. Lancement, avec verification que le processus SURVIT
Write-Host "[4] Lancement de NovaBlock..." -ForegroundColor Cyan
try { Start-Process -FilePath $exePath -ErrorAction Stop } catch { Souci "lancement impossible : $($_.Exception.Message)" }
Start-Sleep -Seconds 6
$proc = @(Get-Process NovaBlock -ErrorAction SilentlyContinue)
if ($proc.Count -gt 0) { OK "$($proc.Count) processus en cours" }
else { Souci "le processus a demarre puis s'est arrete - voir $nb\novablock.log" }

# 5. Heartbeat
Write-Host "[5] Attente du heartbeat (30 s max)..." -ForegroundColor Cyan
$hb = Join-Path $nb 'watchdog.heartbeat'
$frais = $false
for ($w = 0; $w -lt 30; $w += 3) {
    Start-Sleep -Seconds 3
    if (Test-Path $hb) {
        $ts = 0; [int]::TryParse((Get-Content $hb -ErrorAction SilentlyContinue), [ref]$ts) | Out-Null
        $age = [int]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) - $ts
        if ($age -lt 60) { OK "heartbeat frais ($age s)"; $frais = $true; break }
    }
}
if (-not $frais) { Souci "pas de heartbeat frais - la tache planifiee reessaiera dans 1 min" }

# 6. Etat reel de la protection
Write-Host "[6] Verification de la protection..." -ForegroundColor Cyan
$dns = (Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.ServerAddresses.Count -gt 0 } |
        Select-Object -First 1 -ExpandProperty ServerAddresses) -join ', '
if ($dns -match '1\.1\.1\.3|1\.0\.0\.3|9\.9\.9\.11') { OK "DNS familial : $dns" }
else { Souci "DNS non filtre : $dns (NovaBlock le remettra sous 30 s)" }

$h = "$env:windir\System32\drivers\etc\hosts"
$ko = [math]::Round((Get-Item $h).Length / 1KB, 0)
if ($ko -gt 500) { OK "bloc hosts present ($ko Ko)" } else { Info "hosts a $ko Ko - couche hosts inactive" }

try {
    $fw = New-Object -ComObject HNetCfg.FwPolicy2
    $n = $fw.Rules.Count
    if ($n -gt 5000) { Souci "$n regles pare-feu - doublons, lance REPARE_INTERNET.ps1" }
    else { OK "$n regles pare-feu (normal)" }
} catch { Info "comptage des regles indisponible" }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
if ($script:problemes -eq 0) {
    Write-Host "NOVABLOCK REACTIVE - tout est verifie." -ForegroundColor Green
} else {
    Write-Host "$($script:problemes) point(s) a surveiller - voir les lignes !! ci-dessus." -ForegroundColor Yellow
    Write-Host "Le watchdog SYSTEM reessaie chaque minute." -ForegroundColor DarkGray
}
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Read-Host "Entree pour fermer"
