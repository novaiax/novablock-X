# ============================================================
# NovaBlock - EMERGENCY RESET (interface securisee)
# ============================================================
# Le reset lui-meme n a PAS change : sa logique est embarquee plus bas,
# a l identique, dans $CORE_SCRIPT. Cette interface ajoute uniquement une
# couche de friction devant, pour qu un reset ne parte jamais sur un coup
# de tete :
#
#   1. un code aleatoire de 30 caracteres est genere a chaque lancement
#   2. il faut le retaper a la main, caractere par caractere
#   3. tout copier-coller est neutralise (clavier, menu contextuel, glisser)
#   4. le bouton reste inactif tant que la saisie n est pas exacte
#
# La logique du reset est volontairement DANS ce fichier et non a cote :
# un fichier separe se lancerait directement et sauterait le defi.
#
# Usage : double-clic sur EMERGENCY_RESET.bat (il s eleve tout seul)
# ============================================================

$ErrorActionPreference = 'Continue'
$ProgressPreference    = 'SilentlyContinue'

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "EMERGENCY_RESET a besoin des droits administrateur. Relance EMERGENCY_RESET.bat, il s eleve tout seul.",
        "NovaBlock - EMERGENCY RESET", 'OK', 'Warning') | Out-Null
    exit 1
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# ============================================================
# LOGIQUE DU RESET - INCHANGEE
# ============================================================
# Contenu repris octet pour octet du EMERGENCY_RESET.ps1 existant.
# Le here-string ci-dessous est litteral : aucune variable n y est
# interpretee, donc aucune commande n est alteree. Il est embarque ici
# plutot que garde dans un fichier a cote, car un fichier separe se
# lancerait directement et sauterait le defi des 30 caracteres.
$CORE_SCRIPT = @'
# ============================================================
# NovaBlock - EMERGENCY RESET
# ============================================================
# Last-resort cleanup. Disables EVERYTHING NovaBlock-related plus
# the Windows Firewall so Chrome and other apps work IMMEDIATELY.
# NovaBlock is left fully OFF. Relaunch NovaBlock.exe (admin) when
# you want protection back.
#
# Designed to be portable: no hardcoded paths, uses %WINDIR% and
# %PROGRAMDATA%, runs on any Windows install with NovaBlock.
#
# Two ways to run:
#   1) Local: double-click EMERGENCY_RESET.bat (auto-elevates)
#   2) Remote one-liner (PowerShell admin):
#      iex (irm https://raw.githubusercontent.com/novaiax/novablock-X/main/EMERGENCY_RESET.ps1)
# ============================================================

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

# Self-elevate check
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "This script needs admin rights." -ForegroundColor Red
    Write-Host "Reopen PowerShell as Administrator and rerun:" -ForegroundColor Yellow
    Write-Host "  iex (irm https://raw.githubusercontent.com/novaiax/novablock-X/main/EMERGENCY_RESET.ps1)" -ForegroundColor Cyan
    exit 1
}

Write-Host "=== EMERGENCY RESET ===" -ForegroundColor Yellow

# 1. Kill NovaBlock
Write-Host "[1] Killing NovaBlock processes + tasks..." -ForegroundColor Cyan
schtasks /End /TN NovaBlockWatchdog 2>$null | Out-Null
schtasks /End /TN NovaBlockApp 2>$null | Out-Null
Stop-Process -Name NovaBlock -Force -ErrorAction SilentlyContinue
Stop-Process -Name "NovaBlock-Dev" -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
Write-Host "    OK" -ForegroundColor Green

# 2. Disable scheduled tasks entirely (prevent auto-restart)
Write-Host "[2] Disabling NovaBlock scheduled tasks..." -ForegroundColor Cyan
schtasks /Change /TN NovaBlockWatchdog /Disable 2>$null | Out-Null
schtasks /Change /TN NovaBlockApp /Disable 2>$null | Out-Null
Write-Host "    OK" -ForegroundColor Green

# 3. Mass-wipe firewall rules via COM
# WARNING - do NOT do this:
#     $fw.Rules | Where-Object { $_.Name -like 'NovaBlock_DoH_*' }
# Piping the COM collection makes PowerShell wrap EVERY Windows firewall rule
# (several thousand on a normal install) in a PSObject and run full member
# discovery on each one. That took minutes to hours here, with no output, and
# looked like a freeze. NovaBlock's rule names are deterministic, so we rebuild
# them and call Remove() by name: O(1) per rule, zero enumeration.
Write-Host "[3] Wiping NovaBlock firewall rules..." -ForegroundColor Cyan
$dohIps = @(
    '1.1.1.1','1.0.0.1','1.1.1.2','1.0.0.2','1.1.1.3','1.0.0.3',
    '162.159.36.5','162.159.46.5','172.64.36.5','172.64.46.5',
    '8.8.8.8','8.8.4.4','2001:4860:4860::8888','2001:4860:4860::8844',
    '9.9.9.9','149.112.112.112','9.9.9.10','149.112.112.10',
    '9.9.9.11','149.112.112.11',
    '208.67.222.222','208.67.220.220',
    '45.90.28.0','45.90.30.0',
    '94.140.14.14','94.140.15.15'
)
$protos = @('TCP443','TCP853','UDP443')
try {
    $fw = New-Object -ComObject HNetCfg.FwPolicy2
    $total = $dohIps.Count * $protos.Count
    $removed = 0
    $i = 0
    foreach ($ip in $dohIps) {
        $safe = $ip.Replace(':','_').Replace('.','_')
        foreach ($pr in $protos) {
            $i++
            $name = 'NovaBlock_DoH_' + $pr + '_' + $safe
            try { $fw.Rules.Remove($name); $removed++ } catch { }
        }
        Write-Host ("    ... {0}/{1} verifiees, {2} supprimees" -f $i, $total, $removed) -ForegroundColor DarkGray
    }
    Write-Host "    OK - $removed regles supprimees sur $total" -ForegroundColor Green
} catch {
    Write-Host "    COM indisponible: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "    L'etape 4 desactive le pare-feu entier, les regles seront sans effet." -ForegroundColor DarkGray
}

# 4. DISABLE Windows Firewall entirely (TEMPORARY)
Write-Host "[4] Disabling Windows Firewall (TEMPORARY)..." -ForegroundColor Cyan
netsh advfirewall set allprofiles state off | Out-Null
Write-Host "    OK - firewall OFF" -ForegroundColor Green

# 5. Reset DNS to DHCP everywhere
Write-Host "[5] Resetting DNS to DHCP on all active interfaces..." -ForegroundColor Cyan
$adapters = @(Get-NetAdapter | Where-Object { $_.Status -eq 'Up' })
foreach ($a in $adapters) {
    try {
        Set-DnsClientServerAddress -InterfaceAlias $a.Name -ResetServerAddresses -ErrorAction Stop
        Write-Host "    OK - $($a.Name)" -ForegroundColor Green
    } catch {
        Write-Host "    FAIL - $($a.Name): $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# 6. Flush DNS + ARP
Write-Host "[6] Flushing DNS + ARP..." -ForegroundColor Cyan
ipconfig /flushdns | Out-Null
Clear-DnsClientCache -ErrorAction SilentlyContinue
arp -d '*' 2>$null | Out-Null
Write-Host "    OK" -ForegroundColor Green

# 7. Clean hosts file of ALL NovaBlock + YouTube Restricted entries
Write-Host "[7] Cleaning hosts file..." -ForegroundColor Cyan
$hosts = "$env:windir\System32\drivers\etc\hosts"
takeown /f $hosts /a 2>&1 | Out-Null
icacls $hosts /grant 'Administrators:F' 2>&1 | Out-Null
try {
    $content = Get-Content $hosts -ErrorAction Stop
    Copy-Item $hosts "$hosts.bak" -Force
    # Remove everything between NovaBlock markers + the YouTube Restricted line
    $cleaned = New-Object System.Collections.ArrayList
    $inBlock = $false
    foreach ($line in $content) {
        if ($line -match '=== NOVABLOCK START ===') { $inBlock = $true; continue }
        if ($line -match '=== NOVABLOCK END ===')   { $inBlock = $false; continue }
        if ($inBlock) { continue }
        if ($line -match '216\.239\.38\.119') { continue }
        [void]$cleaned.Add($line)
    }
    $cleaned | Set-Content $hosts -Encoding ASCII
    Write-Host "    OK - NovaBlock block + YouTube Restricted removed from hosts" -ForegroundColor Green
} catch {
    Write-Host "    FAIL: $($_.Exception.Message)" -ForegroundColor Yellow
}

# 8. Remove ALL NovaBlock browser policies
Write-Host "[8] Removing browser policies..." -ForegroundColor Cyan
$vendors = @(
    'HKLM:\SOFTWARE\Policies\Google\Chrome',
    'HKLM:\SOFTWARE\Policies\Microsoft\Edge',
    'HKLM:\SOFTWARE\Policies\BraveSoftware\Brave',
    'HKLM:\SOFTWARE\Policies\Opera Software\Opera Stable',
    'HKLM:\SOFTWARE\Policies\Mozilla\Firefox'
)
$policyValues = @('ForceYouTubeRestrict','ForceGoogleSafeSearch','DnsOverHttpsMode','BuiltInDnsClientEnabled','IncognitoModeAvailability','InPrivateModeAvailability','ForceBingSafeSearch','DisablePrivateBrowsing')
foreach ($v in $vendors) {
    foreach ($val in $policyValues) {
        try { Remove-ItemProperty -Path $v -Name $val -ErrorAction Stop } catch {}
    }
    # Firefox DoH path is nested
    try { Remove-ItemProperty -Path "$v\DNSOverHTTPS" -Name 'Enabled' -ErrorAction Stop } catch {}
    try { Remove-ItemProperty -Path "$v\DNSOverHTTPS" -Name 'Locked'  -ErrorAction Stop } catch {}
    # Reddit URLBlocklist subkey - wipe NovaBlock's numeric entries
    $sub = "$v\URLBlocklist"
    try {
        if (Test-Path $sub) {
            Get-Item $sub | ForEach-Object {
                $_.GetValueNames() | Where-Object { $_ -match '^\d+$' } |
                    ForEach-Object { Remove-ItemProperty -Path $sub -Name $_ -ErrorAction SilentlyContinue }
            }
        }
    } catch {}
}
Write-Host "    OK - browser policies cleared (including Reddit URLBlocklist)" -ForegroundColor Green

# 9. Kill all browsers so they restart fresh
Write-Host "[9] Killing browsers (they will need to be reopened)..." -ForegroundColor Cyan
foreach ($p in @('chrome','msedge','brave','firefox','opera','vivaldi')) {
    Stop-Process -Name $p -Force -ErrorAction SilentlyContinue
}
Write-Host "    OK" -ForegroundColor Green

# 10. Verify connectivity
Write-Host "[10] Verifying connectivity..." -ForegroundColor Cyan
$pIP   = Test-Connection 8.8.8.8    -Count 1 -Quiet -ErrorAction SilentlyContinue
$pName = Test-Connection google.com -Count 1 -Quiet -ErrorAction SilentlyContinue
if ($pIP -and $pName) {
    Write-Host "    OK - internet alive (IP + DNS)" -ForegroundColor Green
} elseif ($pIP) {
    Write-Host "    PARTIAL - IP works, DNS resolution fails" -ForegroundColor Yellow
} else {
    Write-Host "    FAIL - no connectivity" -ForegroundColor Red
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "EVERYTHING OFF. Open Chrome - should work now." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "Reactivate later via: NovaBlock.exe (admin) - it will re-arm everything." -ForegroundColor DarkGray
Write-Host ""
Start-Sleep -Seconds 10
'@


# --- Generation du code : 30 caracteres, aleatoire cryptographique ---
# Au moins un caractere de chaque famille, puis melange Fisher-Yates
# alimente par le meme generateur cryptographique.
# Les caracteres ambigus (l/I/1, O/0) sont exclus : le code doit etre
# penible a saisir, pas impossible a lire.
function New-ChallengeCode {
    $minuscules = 'abcdefghijkmnopqrstuvwxyz'
    $majuscules = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
    $chiffres   = '23456789'
    $speciaux   = [char[]]@('!','@','#','%','&','*','+','-','=','?')
    $speciaux   = -join $speciaux
    $toutes     = $minuscules + $majuscules + $chiffres + $speciaux

    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $tirer = {
        param([string]$jeu)
        $b = New-Object byte[] 4
        $rng.GetBytes($b)
        $v = [System.BitConverter]::ToUInt32($b, 0)
        $jeu[[int]($v % [uint32]$jeu.Length)]
    }

    $chars = New-Object System.Collections.Generic.List[char]
    $chars.Add((& $tirer $minuscules))
    $chars.Add((& $tirer $majuscules))
    $chars.Add((& $tirer $chiffres))
    $chars.Add((& $tirer $speciaux))
    while ($chars.Count -lt 30) { $chars.Add((& $tirer $toutes)) }

    for ($i = $chars.Count - 1; $i -gt 0; $i--) {
        $b = New-Object byte[] 4
        $rng.GetBytes($b)
        $j = [int]([System.BitConverter]::ToUInt32($b, 0) % [uint32]($i + 1))
        $tmp = $chars[$i]; $chars[$i] = $chars[$j]; $chars[$j] = $tmp
    }
    $rng.Dispose()
    -join $chars
}

$script:CODE = New-ChallengeCode

# --- Palette ---
$FOND     = [System.Drawing.Color]::FromArgb(24, 24, 28)
$CARTE    = [System.Drawing.Color]::FromArgb(34, 34, 40)
$CHAMP    = [System.Drawing.Color]::FromArgb(16, 16, 20)
$TEXTE    = [System.Drawing.Color]::FromArgb(232, 232, 238)
$DISCRET  = [System.Drawing.Color]::FromArgb(150, 150, 160)
$ROUGE    = [System.Drawing.Color]::FromArgb(232, 84, 84)
$VERT     = [System.Drawing.Color]::FromArgb(110, 220, 150)
$AMBRE    = [System.Drawing.Color]::FromArgb(240, 190, 100)

$form = New-Object System.Windows.Forms.Form
$form.Text            = "NovaBlock - EMERGENCY RESET"
$form.Size            = New-Object System.Drawing.Size(840, 760)
$form.StartPosition   = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox     = $false
$form.BackColor       = $FOND

function Add-Lbl($parent, $texte, $x, $y, $w, $h, $taille, $gras, $couleur) {
    $l = New-Object System.Windows.Forms.Label
    $l.Text      = $texte
    $l.Location  = New-Object System.Drawing.Point($x, $y)
    $l.Size      = New-Object System.Drawing.Size($w, $h)
    $st = if ($gras) { [System.Drawing.FontStyle]::Bold } else { [System.Drawing.FontStyle]::Regular }
    $l.Font      = New-Object System.Drawing.Font("Segoe UI", $taille, $st)
    $l.ForeColor = $couleur
    $l.BackColor = [System.Drawing.Color]::Transparent
    $parent.Controls.Add($l)
    $l
}

# --- Bandeau ---
$bandeau = New-Object System.Windows.Forms.Panel
$bandeau.Location  = New-Object System.Drawing.Point(0, 0)
$bandeau.Size      = New-Object System.Drawing.Size(840, 88)
$bandeau.BackColor = [System.Drawing.Color]::FromArgb(44, 22, 24)
$form.Controls.Add($bandeau)

$accent = New-Object System.Windows.Forms.Panel
$accent.Location  = New-Object System.Drawing.Point(0, 0)
$accent.Size      = New-Object System.Drawing.Size(6, 88)
$accent.BackColor = $ROUGE
$bandeau.Controls.Add($accent)

$null = Add-Lbl $bandeau "EMERGENCY RESET" 28 16 700 34 17 $true $ROUGE
$null = Add-Lbl $bandeau "Desactive completement NovaBlock : pare-feu, DNS, blocage hosts, politiques navigateur." 28 50 780 20 9 $false $DISCRET

# --- Etape 1 ---
$null = Add-Lbl $form "ETAPE 1   Recopie ce code a la main" 28 106 500 22 10 $true $AMBRE
$null = Add-Lbl $form "Le copier-coller est desactive. Les caracteres ambigus sont exclus du code." 28 128 760 18 8 $false $DISCRET

$carteCode = New-Object System.Windows.Forms.Panel
$carteCode.Location  = New-Object System.Drawing.Point(28, 152)
$carteCode.Size      = New-Object System.Drawing.Size(780, 60)
$carteCode.BackColor = $CHAMP
$form.Controls.Add($carteCode)

# Un Label ne permet ni selection ni copie, contrairement a un champ texte.
$lblCode = New-Object System.Windows.Forms.Label
$lblCode.Text      = $script:CODE
$lblCode.Font      = New-Object System.Drawing.Font("Consolas", 16, [System.Drawing.FontStyle]::Bold)
$lblCode.ForeColor = $VERT
$lblCode.BackColor = [System.Drawing.Color]::Transparent
$lblCode.TextAlign = 'MiddleCenter'
$lblCode.Location  = New-Object System.Drawing.Point(0, 0)
$lblCode.Size      = New-Object System.Drawing.Size(780, 60)
$carteCode.Controls.Add($lblCode)

$saisie = New-Object System.Windows.Forms.TextBox
$saisie.Font        = New-Object System.Drawing.Font("Consolas", 16, [System.Drawing.FontStyle]::Bold)
$saisie.Location    = New-Object System.Drawing.Point(28, 222)
$saisie.Size        = New-Object System.Drawing.Size(780, 42)
$saisie.BackColor   = $CHAMP
$saisie.ForeColor   = $TEXTE
$saisie.BorderStyle = 'FixedSingle'
$saisie.TextAlign   = 'Center'
$saisie.MaxLength   = 30
# ShortcutsEnabled a false neutralise Ctrl+C, Ctrl+V, Ctrl+X, Ctrl+Z,
# Ctrl+Inser et Maj+Inser dans un TextBox WinForms.
$saisie.ShortcutsEnabled = $false
# Menu contextuel vide : plus de Copier / Coller au clic droit.
$saisie.ContextMenuStrip = New-Object System.Windows.Forms.ContextMenuStrip
$saisie.AllowDrop = $false
$form.Controls.Add($saisie)

$jauge = New-Object System.Windows.Forms.ProgressBar
$jauge.Location = New-Object System.Drawing.Point(28, 272)
$jauge.Size     = New-Object System.Drawing.Size(780, 6)
$jauge.Minimum  = 0
$jauge.Maximum  = 30
$jauge.Style    = 'Continuous'
$form.Controls.Add($jauge)

$etat = Add-Lbl $form "0 / 30 caracteres" 28 284 780 20 9 $false $DISCRET

# --- Etape 2 ---
$null = Add-Lbl $form "ETAPE 2   Lance le reset" 28 316 500 22 10 $true $AMBRE

$btn = New-Object System.Windows.Forms.Button
$btn.Text      = "Lancer EMERGENCY_RESET"
$btn.Font      = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$btn.Location  = New-Object System.Drawing.Point(28, 342)
$btn.Size      = New-Object System.Drawing.Size(780, 46)
$btn.Enabled   = $false
$btn.FlatStyle = 'Flat'
$btn.FlatAppearance.BorderSize = 0
$btn.BackColor = $CARTE
$btn.ForeColor = $DISCRET
$btn.Cursor    = 'Hand'
$form.Controls.Add($btn)

# --- Journal ---
$null = Add-Lbl $form "JOURNAL D EXECUTION" 28 404 500 20 9 $true $DISCRET

$logs = New-Object System.Windows.Forms.RichTextBox
$logs.Font        = New-Object System.Drawing.Font("Consolas", 9)
$logs.Location    = New-Object System.Drawing.Point(28, 426)
$logs.Size        = New-Object System.Drawing.Size(780, 232)
$logs.BackColor   = $CHAMP
$logs.ForeColor   = $DISCRET
$logs.BorderStyle = 'None'
$logs.ReadOnly    = $true
$logs.ScrollBars  = 'Vertical'
$logs.Text        = "  En attente de la saisie du code..."
$form.Controls.Add($logs)

$final = Add-Lbl $form "" 28 668 780 30 12 $true $TEXTE
$final.TextAlign = 'MiddleCenter'

$aide = Add-Lbl $form "Pour tout remettre en place ensuite : REACTIVATE.bat" 28 702 780 18 8 $false $DISCRET
$aide.TextAlign = 'MiddleCenter'

# --- Blocage du collage, ceinture et bretelles ---
# ShortcutsEnabled couvre deja le clavier, on intercepte quand meme
# explicitement les combinaisons connues.
$saisie.Add_KeyDown({
    $k = $_.KeyCode
    if ($_.Control -and ($k -eq 'V' -or $k -eq 'C' -or $k -eq 'X' -or $k -eq 'Z' -or $k -eq 'Insert')) {
        $_.SuppressKeyPress = $true; $_.Handled = $true
    }
    if ($_.Shift -and $k -eq 'Insert') { $_.SuppressKeyPress = $true; $_.Handled = $true }
})
$saisie.Add_DragEnter({ $_.Effect = [System.Windows.Forms.DragDropEffects]::None })
$saisie.Add_DragDrop({ })

# --- Comparaison stricte, sensible a la casse ---
$saisie.Add_TextChanged({
    $t = $saisie.Text
    $bons = 0
    while ($bons -lt $t.Length -and $bons -lt $script:CODE.Length -and $t[$bons] -ceq $script:CODE[$bons]) { $bons++ }
    $jauge.Value = [Math]::Min($bons, 30)

    if ([string]::Equals($t, $script:CODE, [System.StringComparison]::Ordinal)) {
        $btn.Enabled    = $true
        $btn.BackColor  = $ROUGE
        $btn.ForeColor  = [System.Drawing.Color]::White
        $saisie.ForeColor = $VERT
        $etat.Text      = "Code correct - tu peux lancer le reset"
        $etat.ForeColor = $VERT
        return
    }

    $btn.Enabled   = $false
    $btn.BackColor = $CARTE
    $btn.ForeColor = $DISCRET

    if ($t.Length -eq 0) {
        $saisie.ForeColor = $TEXTE
        $etat.Text        = "0 / 30 caracteres"
        $etat.ForeColor   = $DISCRET
    } elseif ($bons -lt $t.Length) {
        $saisie.ForeColor = $ROUGE
        $etat.Text        = "Erreur au caractere $($bons + 1) - efface et reprends a partir de la"
        $etat.ForeColor   = $ROUGE
    } else {
        $saisie.ForeColor = $TEXTE
        $etat.Text        = "$($t.Length) / 30 caracteres - continue"
        $etat.ForeColor   = $DISCRET
    }
})

# --- Lancement du script existant + affichage en direct ---
$script:proc       = $null
$script:logFile    = $null
$script:tempScript = $null
$script:position   = 0

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 250
$timer.Add_Tick({
    if ($script:logFile -and (Test-Path $script:logFile)) {
        try {
            $fs = [System.IO.File]::Open($script:logFile, 'Open', 'Read', 'ReadWrite')
            if ($fs.Length -gt $script:position) {
                $fs.Seek($script:position, 'Begin') | Out-Null
                $buf = New-Object byte[] ($fs.Length - $script:position)
                $lu  = $fs.Read($buf, 0, $buf.Length)
                $script:position += $lu
                $txt = [System.Text.Encoding]::UTF8.GetString($buf, 0, $lu)
                if ($txt) {
                    $logs.AppendText($txt)
                    $logs.SelectionStart = $logs.TextLength
                    $logs.ScrollToCaret()
                }
            }
            $fs.Close()
        } catch { }
    }
    if ($script:proc -and $script:proc.HasExited) {
        $timer.Stop()
        $btn.Text = "Termine"
        if ($script:proc.ExitCode -eq 0) {
            $final.Text      = "EMERGENCY_RESET termine avec succes"
            $final.ForeColor = $VERT
        } else {
            $final.Text      = "EMERGENCY_RESET termine avec une erreur (code $($script:proc.ExitCode))"
            $final.ForeColor = $ROUGE
        }
        if ($script:tempScript -and (Test-Path $script:tempScript)) {
            Remove-Item $script:tempScript -Force -ErrorAction SilentlyContinue
        }
    }
})

$btn.Add_Click({
    $btn.Enabled      = $false
    $saisie.Enabled   = $false
    $saisie.Text      = ""
    $lblCode.Text     = "reset en cours"
    $btn.Text         = "EMERGENCY_RESET en cours..."
    $btn.BackColor    = $CARTE
    $btn.ForeColor    = $DISCRET
    $etat.Text        = ""
    $jauge.Value      = 30
    $logs.Clear()
    $logs.ForeColor   = $TEXTE
    $final.Text       = ""

    # Le script existant est ecrit tel quel dans un fichier temporaire puis
    # execute. Sa logique n est pas touchee.
    $script:tempScript = Join-Path $env:TEMP ("nb_reset_{0}.ps1" -f ([guid]::NewGuid().ToString('N')))
    $script:logFile    = Join-Path $env:TEMP ("nb_reset_{0}.log" -f ([guid]::NewGuid().ToString('N')))
    Set-Content -Path $script:tempScript -Value $CORE_SCRIPT -Encoding UTF8
    $script:position = 0

    $a = '/c powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" > "{1}" 2>&1' -f $script:tempScript, $script:logFile
    $script:proc = Start-Process -FilePath 'cmd.exe' -ArgumentList $a -WindowStyle Hidden -PassThru
    $timer.Start()
})

$form.Add_Shown({ $saisie.Focus() })
[void]$form.ShowDialog()
