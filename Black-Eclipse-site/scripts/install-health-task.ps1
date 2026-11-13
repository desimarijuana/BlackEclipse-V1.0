# Install a recurring BlackEclipse health check as a Windows Task Scheduler task.
# The Linux equivalent is a cron entry or a systemd timer running health-watch.sh.
#
#   powershell -ExecutionPolicy Bypass -File scripts/install-health-task.ps1 `
#     -HealthUrl http://127.0.0.1:3105/login `
#     -AlertWebhookUrl https://hooks.slack.com/services/...
#
# Without -AlertWebhookUrl no remote human is paged. The wrapper still escalates
# locally, so a failure is not silent: it shows a Windows desktop notification to
# the signed-in operator (scripts/alert-desktop.ps1) and keeps an ALERT-ACTIVE
# marker until the next healthy run. That is visible evidence, but it is still
# not an off-machine page -- pass a Slack/Teams/Discord-compatible webhook to make
# a failure reach a person when nobody is at the machine.
[CmdletBinding()]
param(
  [string]$HealthUrl = "http://127.0.0.1:3000/login",
  [string]$AlertWebhookUrl = "",
  [int]$IntervalMinutes = 5
)

$ErrorActionPreference = "Stop"
$app = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$bash = (Get-Command bash -ErrorAction Stop).Source
$wrapperDir = Join-Path $env:LOCALAPPDATA "BlackEclipse"
New-Item -ItemType Directory -Path $wrapperDir -Force | Out-Null

$winApp = $app -replace "\\", "/"
$posixApp = (& $bash -lc "cygpath -u '$winApp'").Trim()
if (-not $posixApp) { throw "cygpath could not resolve the app path" }

$wrapper = Join-Path $wrapperDir "health-task.cmd"
$logPath = Join-Path $wrapperDir "health.log"
$alertPath = Join-Path $wrapperDir "ALERT-ACTIVE.txt"
$alertScript = Join-Path $app "scripts\alert-desktop.ps1"
$powershell = (Get-Command powershell -ErrorAction Stop).Source
$command = "cd '$posixApp' && HEALTH_URL='$HealthUrl' ALERT_WEBHOOK_URL='$AlertWebhookUrl' ./scripts/health-watch.sh"
@(
  "@echo off",
  "echo [%DATE% %TIME%] >> `"$logPath`"",
  "`"$bash`" -lc `"$command`" >> `"$logPath`" 2>&1",
  "if errorlevel 1 (",
  "  echo [%DATE% %TIME%] health check FAILED - see health.log >> `"$alertPath`"",
  "  `"$powershell`" -NoProfile -ExecutionPolicy Bypass -File `"$alertScript`" -Message `"BlackEclipse health check FAILED on $env:COMPUTERNAME - see health.log`" >> `"$logPath`" 2>&1",
  "  exit /b 1",
  ") else (",
  "  del `"$alertPath`" 2>nul",
  ")"
) | Set-Content -Path $wrapper -Encoding ASCII

$task = "BlackEclipse Health"
& schtasks.exe /Create /F /SC MINUTE /MO $IntervalMinutes /TN $task /TR "`"$wrapper`"" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks /Create failed (exit $LASTEXITCODE)" }
Write-Host "installed '$task' every $IntervalMinutes minute(s)"
Write-Host "health URL: $HealthUrl"
Write-Host "alert webhook: $(if ($AlertWebhookUrl) { 'configured' } else { 'NONE (local desktop alert + log only)' })"
Write-Host "local escalation: desktop notification to the signed-in operator (scripts/alert-desktop.ps1)"
Write-Host "active-alert marker: $alertPath"
Write-Host "log: $logPath"
Write-Host "run it once now: schtasks /Run /TN `"$task`""
