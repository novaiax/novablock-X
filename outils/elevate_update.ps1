param(
    [Parameter(Mandatory = $true)]
    [string]$ScriptPath,
    [string]$LocalApp = '',
    [string]$LocalRecovery = ''
)

$ErrorActionPreference = 'Stop'

try {
    $scriptFullPath = [IO.Path]::GetFullPath($ScriptPath)
    $invokeArguments = @()
    if ($LocalApp -or $LocalRecovery) {
        if (-not $LocalApp -or -not $LocalRecovery) {
            throw 'Les deux artefacts locaux sont requis.'
        }
        $invokeArguments = @(
            '--local',
            [IO.Path]::GetFullPath($LocalApp),
            [IO.Path]::GetFullPath($LocalRecovery)
        )
    }

    $quoteLiteral = {
        param([string]$Value)
        "'" + $Value.Replace("'", "''") + "'"
    }
    $commandParts = @('&', (& $quoteLiteral $scriptFullPath))
    foreach ($argument in $invokeArguments) {
        $commandParts += (& $quoteLiteral $argument)
    }
    $command = ($commandParts -join ' ') + "`nexit `$LASTEXITCODE"
    $encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    $windowsPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    Start-Process -FilePath $windowsPowerShell `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encodedCommand) `
        -Verb RunAs -ErrorAction Stop | Out-Null
    exit 0
} catch {
    Write-Error "Elevation de la mise a jour impossible : $($_.Exception.Message)"
    exit 1
}
