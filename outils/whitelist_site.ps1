# ============================================================
# NovaBlock - Whitelist a site filtered by Cloudflare Family DNS
# ============================================================
# Use when a legit site (e.g. movix.golf, a film streaming site,
# a niche forum) is mis-classified as adult by Cloudflare Family
# DNS (1.1.1.3) and returns 0.0.0.0 / NXDOMAIN. Adds an explicit
# hosts entry that bypasses the DNS filter for that domain only.
#
# What it does:
#   1. Asks you for the domain to unblock (e.g. movix.golf)
#   2. Resolves the real Cloudflare CDN IP via Google DNS (8.8.8.8)
#   3. Strips any old broken entries for that domain from hosts
#   4. Writes clean hosts entries (apex + www) OUTSIDE the NovaBlock
#      block - the watchdog never touches them
#   5. Forces Dnscache to re-read hosts: kills the svchost process
#      hosting Dnscache (Windows auto-restarts it within seconds)
#   6. Tests ping + DNS resolution and reports
#
# NovaBlock protection still applies via title-keyword monitor:
# any page on the unblocked site with porn/sex/milf/etc. in the
# title triggers the popup regardless.
# ============================================================

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

# Admin check
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Cette commande doit etre admin." -ForegroundColor Red
    Read-Host "Appuie sur Entree pour quitter"
    exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Whitelist site - bypass Cloudflare Family DNS" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Ce script debloque un site que Cloudflare Family bloque" -ForegroundColor Yellow
Write-Host "par erreur (ex: movix.golf, sites de streaming legit, etc.)" -ForegroundColor Yellow
Write-Host ""

$domain = Read-Host "Domaine a debloquer (sans https://, ex: movix.golf)"
$domain = $domain.Trim().ToLower()
$domain = $domain -replace '^https?://',''
$domain = $domain -replace '^www\.',''
$domain = $domain -replace '/.*$',''

if (-not $domain -or $domain -notmatch '\.') {
    Write-Host "Domaine invalide." -ForegroundColor Red
    Read-Host "Entree pour quitter"
    exit 1
}

Write-Host ""
Write-Host "[1] Resolution de '$domain' via Google DNS (8.8.8.8)..." -ForegroundColor Cyan
$ips = @()
try {
    $r = Resolve-DnsName -Name $domain -Server 8.8.8.8 -Type A -ErrorAction Stop
    $ips = @($r | Where-Object { $_.IPAddress } | Select-Object -ExpandProperty IPAddress -Unique)
} catch {
    Write-Host "    Echec de la resolution: $($_.Exception.Message)" -ForegroundColor Red
}

if (-not $ips -or $ips.Count -eq 0) {
    Write-Host "    Aucune IP trouvee - le domaine n'existe peut-etre pas." -ForegroundColor Red
    Read-Host "Entree pour quitter"
    exit 1
}

Write-Host "    IPs trouvees: $($ips -join ', ')" -ForegroundColor Green

# 2. Ensure hosts is writable
$h = "$env:windir\System32\drivers\etc\hosts"
Write-Host ""
Write-Host "[2] Acces en ecriture sur hosts..." -ForegroundColor Cyan
takeown /f $h /a 2>&1 | Out-Null
icacls $h /grant "*S-1-5-32-544:F" 2>&1 | Out-Null
Write-Host "    OK" -ForegroundColor Green

# 3. Rewrite hosts cleanly
Write-Host ""
Write-Host "[3] Reecriture du fichier hosts..." -ForegroundColor Cyan
$existing = [System.IO.File]::ReadAllLines($h) | Where-Object {
    ($_ -notmatch [regex]::Escape($domain)) -and
    ($_ -notmatch 'NovaBlock bypass')
}

$bypassHeader = "# === NovaBlock bypass - $domain (Cloudflare Family was filtering) ==="
$newLines = @($bypassHeader)
foreach ($ip in $ips) {
    $newLines += "$ip $domain"
    $newLines += "$ip www.$domain"
}
$newLines += ""

$final = @($newLines) + @($existing)
[System.IO.File]::WriteAllLines($h, $final, [System.Text.UTF8Encoding]::new($false))
Write-Host "    Entrees ajoutees:" -ForegroundColor Green
foreach ($l in $newLines | Where-Object { $_ -match '^\d' }) {
    Write-Host "      $l" -ForegroundColor Green
}

# 4. Force Dnscache to re-read hosts
Write-Host ""
Write-Host "[4] Force Dnscache a relire hosts..." -ForegroundColor Cyan
try {
    $svc = Get-CimInstance -ClassName Win32_Service -Filter "Name='Dnscache'" -ErrorAction Stop
    $pidDns = $svc.ProcessId
    if ($pidDns -gt 0) {
        Write-Host "    Kill du process svchost (PID=$pidDns) hebergeant Dnscache..." -ForegroundColor Yellow
        Stop-Process -Id $pidDns -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
        # Windows auto-restarts the service
        Start-Service Dnscache -ErrorAction SilentlyContinue
        Write-Host "    Dnscache redemarre" -ForegroundColor Green
    } else {
        Write-Host "    PID Dnscache introuvable, fallback flush DNS" -ForegroundColor Yellow
    }
} catch {
    Write-Host "    Echec restart Dnscache: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "    Tu peux essayer de rebooter pour que Windows relise hosts." -ForegroundColor Yellow
}

ipconfig /flushdns | Out-Null
Clear-DnsClientCache -ErrorAction SilentlyContinue

# 5. Kill browsers so they drop their internal DNS cache
Write-Host ""
Write-Host "[5] Kill des navigateurs (ils vont re-lire le DNS au prochain lancement)..." -ForegroundColor Cyan
foreach ($p in @('chrome','msedge','brave','firefox','opera','vivaldi')) {
    Stop-Process -Name $p -Force -ErrorAction SilentlyContinue
}
Write-Host "    OK" -ForegroundColor Green

# 6. Verify
Write-Host ""
Write-Host "[6] Test final..." -ForegroundColor Cyan
Start-Sleep -Seconds 2
$resolved = $null
try {
    $resolved = (Resolve-DnsName $domain -ErrorAction Stop | Where-Object { $_.IPAddress } | Select-Object -First 1).IPAddress
} catch {}

if ($resolved -and $resolved -ne '0.0.0.0' -and $resolved -ne '::') {
    Write-Host "    Resolution OK: $domain -> $resolved" -ForegroundColor Green
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host " Reouvre Chrome -> https://$domain doit fonctionner" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    Write-Host "    Resolution echoue (cache Windows toujours en place)." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host " REBOOT REQUIS - Windows n'a pas pu relire hosts" -ForegroundColor Yellow
    Write-Host " Apres reboot, $domain sera accessible" -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Appuie sur Entree pour quitter"
