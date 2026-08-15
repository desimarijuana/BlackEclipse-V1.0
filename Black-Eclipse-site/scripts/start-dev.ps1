# Starts the Next.js dev server as a detached background process so it keeps
# running even after the launching shell/terminal exits or times out.
# Logs go to dev_output.log in the project root.
#
# Usage:  powershell -ExecutionPolicy Bypass -File scripts/start-dev.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# If already listening on 3000, do nothing.
$existing = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Dev server already running on port 3000 (PID $($existing.OwningProcess))."
    exit 0
}

# Launch detached (hidden window) so it survives this shell.
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c npm run dev > dev_output.log 2>&1" `
    -WorkingDirectory $root `
    -WindowStyle Hidden

Write-Host "Dev server starting in background... log: $root\dev_output.log"
