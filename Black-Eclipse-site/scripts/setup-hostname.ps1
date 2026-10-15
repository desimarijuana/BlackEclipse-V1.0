# Adds (idempotently) the local hostname alias used by scripts/local-proxy.js to
# the Windows hosts file, so http://blackeclipse resolves to this machine.
#
# Self-elevating: run it from a normal shell and approve the UAC prompt.
#
#   npm run setup:hostname
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-hostname.ps1
#
# It only appends a single line when the entry is missing and then flushes the
# DNS cache. Nothing else in the hosts file is touched.

param([string]$Name = "blackeclipse")

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
    Write-Host "Requesting administrator rights to edit the hosts file..."
    $relaunch = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath, "-Name", $Name)
    $proc = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru -ArgumentList $relaunch
    exit $proc.ExitCode
}

$hosts = "$env:SystemRoot\System32\drivers\etc\hosts"
$line = "127.0.0.1 $Name"
$pattern = "^\s*127\.0\.0\.1\s+$([regex]::Escape($Name))\s*(#.*)?$"

if (Select-String -Path $hosts -Pattern $pattern -Quiet) {
    Write-Host "Already configured: $line"
} else {
    Add-Content -Path $hosts -Value "`r`n$line`t# BlackEclipse local hostname (scripts/local-proxy.js)"
    Write-Host "Added to hosts: $line"
}

ipconfig /flushdns | Out-Null
Write-Host "Done. Verify with:  ping $Name"
