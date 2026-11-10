# Keep BlackEclipse running as a production server on Windows, without admin.
#
# Why this shape: the soak exit gate needs one uninterrupted week, and a dev
# server restarts on every edit (and dies with its terminal). This registers a
# per-user scheduled task that RUNS the server in the foreground, with:
#   * a 2-minute repeating trigger, so a crash is retried;
#   * MultipleInstances = IgnoreNew, so the trigger never starts a second copy
#     while the first is still serving;
#   * ExecutionTimeLimit = unlimited, so a week-long run is not cut at 72h.
# No elevation is required for a per-user task.
#
#   powershell -ExecutionPolicy Bypass -File scripts/install-app-task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/install-app-task.ps1 -Port 3100
#
# Prerequisites: `npm run build` produced `.next` in this folder.
[CmdletBinding()]
param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 3100,
  [string]$TaskName = "BlackEclipse App",
  [int]$IntervalMinutes = 2,
  [string]$AppPath = "",
  [string]$DataDir = ""
)

$ErrorActionPreference = "Stop"
$app = if ($AppPath) { (Resolve-Path $AppPath).Path } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
if (-not (Test-Path (Join-Path $app ".next\BUILD_ID"))) {
  throw "no production build at $app\.next - run 'npm run build' first"
}
$node = (Get-Command node -ErrorAction Stop).Source
$next = Join-Path $app "node_modules\next\dist\bin\next"
if (-not (Test-Path $next)) { throw "next CLI not found at $next" }

$wrapperDir = Join-Path $env:LOCALAPPDATA "BlackEclipse"
New-Item -ItemType Directory -Path $wrapperDir -Force | Out-Null
$wrapper = Join-Path $wrapperDir "app-task.cmd"
$log = Join-Path $wrapperDir "app.log"
$healthUrl = "http://${HostName}:$Port/login"

@(
  "@echo off",
  "rem Start the production server only when it is not already answering.",
  "curl -s -o nul -m 5 `"$healthUrl`"",
  "if not errorlevel 1 goto :eof",
  "echo [%DATE% %TIME%] starting BlackEclipse on ${HostName}:$Port >> `"$log`"",
  "cd /d `"$app`"",
  $(if ($DataDir) { "set `"BE_DATA_DIR=$((Resolve-Path $DataDir).Path)`"" } else { "rem BE_DATA_DIR unset - data lives beside the app" }),
  "start `"BlackEclipse`" /min cmd /c `"`"$node`" `"$next`" start -H $HostName -p $Port >> `"$log`" 2>&1`""
) | Set-Content -Path $wrapper -Encoding ASCII

# Non-elevated recurring watchdog (same mechanism as the health watch). The task
# itself is short-lived; the server it starts is detached and outlives it, so a
# 72-hour task limit cannot cut the soak short.
& schtasks.exe /Create /F /SC MINUTE /MO $IntervalMinutes /TN $TaskName /TR "`"$wrapper`"" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks /Create failed (exit $LASTEXITCODE)" }

# Sign-in recovery, no admin needed.
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "BlackEclipse.cmd"
Copy-Item $wrapper $shortcutPath -Force

# Start it now (the writer is a no-op if the server already answers).
& schtasks.exe /Run /TN $TaskName | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks /Run failed (exit $LASTEXITCODE)" }

Write-Host "installed '$TaskName' every $IntervalMinutes minute(s) and at sign-in"
Write-Host "url: $healthUrl"
Write-Host "wrapper: $wrapper"
Write-Host "startup: $shortcutPath"
Write-Host "log: $log"
Write-Host "state: schtasks /Query /TN '$TaskName' /FO LIST"
