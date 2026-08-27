# ============================================================
# NovaBlock - Reparation du demarrage reseau lent
# ============================================================
# A lancer sur toute machine ou le reseau reste en "Identification"
# plusieurs minutes apres le demarrage.
#
# Clic droit > Executer avec PowerShell, ou :
#   powershell -ExecutionPolicy Bypass -File REPARE_INTERNET.ps1
# ============================================================

$ErrorActionPreference = 'Continue'

function Titre($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function OK($m)    { Write-Host "  [OK] $m" -ForegroundColor Green }
function Souci($m) { Write-Host "  [!]  $m" -ForegroundColor Yellow }
function Info($m)  { Write-Host "  $m" }

# --- Droits admin ---
$admin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host "Elevation necessaire, relance en administrateur..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList `
        "-NoProfile","-ExecutionPolicy","Bypass","-File","`"$PSCommandPath`""
    exit
}

Write-Host "============================================================"
Write-Host " NovaBlock - Reparation du demarrage reseau"
Write-Host "============================================================"

# --- 0. Fichiers d'etat residuels laisses par un update interrompu ---
Titre "0. Fichiers d'etat residuels"
# Un update.bat interrompu en cours de route laisse deux fichiers derriere lui :
#   shutdown.sentinel : NovaBlock le lit au demarrage et S AUTO-TERMINE.
#                       Tant qu'il traine, l'app ne tourne plus du tout.
#   update.lock       : bloque toute nouvelle tentative d'update pendant 30 min.
$nbDir = "$env:ProgramData\NovaBlock"
foreach ($f in @('shutdown.sentinel','update.lock')) {
    $fp = Join-Path $nbDir $f
    if (Test-Path $fp) {
        $age = [int]((Get-Date) - (Get-Item $fp).LastWriteTime).TotalMinutes
        Souci "$f present (depuis $age min) - residu d'un update interrompu"
        try {
            Remove-Item $fp -Force -ErrorAction Stop
            OK "  $f supprime"
        } catch {
            Souci "  suppression impossible : $($_.Exception.Message)"
        }
    } else {
        OK "$f absent (normal)"
    }
}

# --- 1. Etat du dernier demarrage ---
Titre "1. Dernier demarrage"
$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
Info ("Demarrage : {0:dd/MM HH:mm:ss}" -f $boot)
$id = Get-WinEvent -FilterHashtable @{
        LogName='Microsoft-Windows-NetworkProfile/Operational'; Id=4002; StartTime=$boot
      } -ErrorAction SilentlyContinue | Sort-Object TimeCreated | Select-Object -First 1
if ($id) {
    $d = [int]($id.TimeCreated - $boot).TotalSeconds
    if ($d -le 20) { OK "Internet disponible en $d s" } else { Souci "Internet disponible en $d s (trop lent)" }
} else {
    Souci "Le reseau n'a pas encore ete identifie sur ce demarrage"
}

# --- 2. Boucle de faux tamper NovaBlock ---
Titre "2. NovaBlock - boucle de fausse detection"
$log = "C:\ProgramData\NovaBlock\novablock.log"
if (Test-Path $log) {
    $stamp = $boot.ToString('yyyy-MM-dd HH:mm')
    $recent = Get-Content $log | Where-Object {
        $_ -match '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}' -and $_.Substring(0,16) -ge $stamp
    }
    $n = @($recent | Select-String 'Hosts block missing').Count
    if ($n -eq 0) {
        OK "Aucune fausse detection - le correctif est actif"
    } else {
        Souci "$n fausses detections depuis le demarrage"
        Info  "  -> NovaBlock n'est PAS a jour sur cette machine."
        Info  "  -> Lance update.bat en administrateur, puis relance ce script."
    }
} else {
    Info "NovaBlock n'est pas installe sur cette machine."
}

# --- 2b. Migration hosts coincee (LA cause du demarrage lent) ---
Titre "2b. Migration hosts en attente"
# Si une migration de whitelist n'a jamais pu s'appliquer, NovaBlock la rejoue
# a CHAQUE demarrage. Elle appelle unlock_hosts_acl(), qui rend le fichier
# lisible par le client DNS ; celui-ci ingere alors les ~77000 entrees et
# s'effondre. Le "ipconfig /flushdns" qui suit reste bloque 30 s, quatre fois.
# La faire aboutir UNE fois suffit a l'arreter definitivement.
$exe = $null
$run = Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run' -ErrorAction SilentlyContinue
if ($run -and $run.NovaBlock) { $exe = ($run.NovaBlock) -replace '"','' }
if ((-not $exe) -or (-not (Test-Path $exe))) {
    $exe = 'D:\code\app\bloqueur distractions\dist\NovaBlock.exe'
}

if (Test-Path $exe) {
    $pending = $false
    if (Test-Path $log) {
        $tail = Get-Content $log -Tail 400 -ErrorAction SilentlyContinue
        if ($tail | Select-String 'still in hosts|Failed to apply hosts block') { $pending = $true }
    }
    if ($pending) {
        Souci "Migration hosts en attente - c'est elle qui ralentit le demarrage."
        Info  "Application en cours (les navigateurs vont se fermer)..."
        & $exe --reapply
        Start-Sleep -Seconds 5
        OK "Migration appliquee - elle ne se rejouera plus au demarrage."
    } else {
        OK "Aucune migration en attente"
    }
} else {
    Souci "NovaBlock.exe introuvable - etape ignoree"
}

# --- 3. Carte reseau : reglages qui perturbent le repeteur/switch ---
Titre "3. Carte reseau"
$props = @{
    '*EEE'               = 'Ethernet economie d energie'
    'EnableGreenEthernet'= 'Ethernet vert'
    '*PMARPOffload'      = 'Decharge ARP'
    '*PMNSOffload'       = 'Decharge NS'
    'S5WakeOnLan'        = 'Wake-on-LAN a l arret'
}
foreach ($ad in Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.Virtual -eq $false }) {
    Info "Carte : $($ad.Name)"
    foreach ($k in $props.Keys) {
        $cur = Get-NetAdapterAdvancedProperty -Name $ad.Name -RegistryKeyword $k -ErrorAction SilentlyContinue
        if ($null -eq $cur) { continue }
        if ($cur.RegistryValue -contains '0') {
            OK "  $($props[$k]) deja desactive"
        } else {
            try {
                Set-NetAdapterAdvancedProperty -Name $ad.Name -RegistryKeyword $k `
                    -RegistryValue '0' -NoRestart -ErrorAction Stop
                OK "  $($props[$k]) desactive"
            } catch {
                Souci "  $($props[$k]) : non modifiable ($($_.Exception.Message))"
            }
        }
    }
}

# --- 4. Cold Turkey : demarrage retarde ---
Titre "4. Cold Turkey"
$ct = Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
      Where-Object { $_.PathName -match 'Cold Turkey' }
if ($ct) {
    foreach ($s in $ct) {
        $reg = "HKLM:\SYSTEM\CurrentControlSet\Services\$($s.Name)"
        $da  = (Get-ItemProperty $reg -ErrorAction SilentlyContinue).DelayedAutostart
        if ($da -eq 1) {
            OK "$($s.Name) deja en demarrage retarde"
        } else {
            & sc.exe config $s.Name start= delayed-auto | Out-Null
            if ($LASTEXITCODE -eq 0) { OK "$($s.Name) passe en demarrage retarde" }
            else { Souci "$($s.Name) : echec du changement" }
        }
    }
} else {
    Info "Cold Turkey n'est pas installe sur cette machine."
}

# --- 5. Journaux de diagnostic ---
Titre "5. Journaux de diagnostic"
foreach ($l in @('Microsoft-Windows-NDIS/Operational',
                 'Microsoft-Windows-Dhcp-Client/Operational')) {
    & wevtutil.exe sl $l /e:true 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { OK "$l active" } else { Souci "$l : echec" }
}

# --- 6. Vitesse DNS ---
Titre "6. Vitesse DNS"
foreach ($n in @('example.com','www.google.com')) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        [System.Net.Dns]::GetHostAddresses($n) | Out-Null
        $sw.Stop()
        $ms = [int]$sw.Elapsed.TotalMilliseconds
        if ($ms -lt 500) { OK "$n : $ms ms" } else { Souci "$n : $ms ms (lent)" }
    } catch { $sw.Stop(); Souci "$n : echec de resolution" }
}

Write-Host ""
Write-Host "============================================================"
Write-Host " Termine. REDEMARRE la machine sans toucher au repeteur,"
Write-Host " puis relance ce script pour verifier le resultat."
Write-Host "============================================================"
Write-Host ""
Read-Host "Appuie sur Entree pour fermer"
