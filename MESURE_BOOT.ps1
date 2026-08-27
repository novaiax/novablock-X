# NovaBlock - Mesure du temps de mise en service du reseau apres demarrage
# Lancer apres un redemarrage. Aucun droit admin requis.

$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
Write-Host ""
Write-Host "=== MESURE BOOT RESEAU ===" -ForegroundColor Cyan
Write-Host ("Demarrage : {0:HH:mm:ss}" -f $boot)

# Moment ou le reseau est passe "Identified"
$id = Get-WinEvent -FilterHashtable @{
    LogName='Microsoft-Windows-NetworkProfile/Operational'; Id=4002; StartTime=$boot
} -ErrorAction SilentlyContinue | Sort-Object TimeCreated | Select-Object -First 1

if ($id) {
    $delta = ($id.TimeCreated - $boot).TotalSeconds
    $col = if ($delta -le 20) { 'Green' } elseif ($delta -le 60) { 'Yellow' } else { 'Red' }
    Write-Host ("Internet  : {0:HH:mm:ss}" -f $id.TimeCreated)
    Write-Host ("DELAI     : {0:N0} secondes" -f $delta) -ForegroundColor $col
} else {
    Write-Host "Internet  : pas encore identifie" -ForegroundColor Red
}

# Coupures physiques du lien (0 attendu si tu n'as pas touche au repeteur)
$down = Get-WinEvent -FilterHashtable @{
    LogName='Microsoft-Windows-NetworkProfile/Operational'; Id=10001; StartTime=$boot
} -ErrorAction SilentlyContinue
Write-Host ("Coupures lien : {0}  (0 attendu)" -f @($down).Count)

# Blocages du client DNS
$dns = Get-WinEvent -FilterHashtable @{
    LogName='System'; ProviderName='Service Control Manager'; Id=7011; StartTime=$boot
} -ErrorAction SilentlyContinue
Write-Host ("Blocages Dnscache : {0}  (0 attendu, c'etait 20)" -f @($dns).Count)

# Boucle de faux tamper - doit etre a 0 apres update_local.bat
$log = "C:\ProgramData\NovaBlock\novablock.log"
if (Test-Path $log) {
    $stamp = $boot.ToString('yyyy-MM-dd HH:mm')
    $lines = Get-Content $log | Where-Object {
        $_ -match '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}' -and $_.Substring(0,16) -ge $stamp
    }
    $false_tamper = @($lines | Select-String 'Hosts block missing').Count
    $col = if ($false_tamper -eq 0) { 'Green' } else { 'Red' }
    Write-Host ("Faux tampers hosts : {0}  (0 attendu si le correctif est actif)" -f $false_tamper) -ForegroundColor $col
}

# Vitesse DNS
Write-Host ""
Write-Host "--- Vitesse DNS ---"
foreach ($n in @('example.com','www.google.com','github.com')) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try { [System.Net.Dns]::GetHostAddresses($n) | Out-Null; $sw.Stop()
          Write-Host ("  {0,-18} {1,7:N3} s" -f $n, $sw.Elapsed.TotalSeconds) }
    catch { $sw.Stop(); Write-Host ("  {0,-18} ECHEC" -f $n) -ForegroundColor Red }
}
Write-Host ""
