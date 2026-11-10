# Install a recurring BlackEclipse health check as a Windows Task Scheduler task.
# The Linux equivalent is a cron entry or a systemd timer running health-watch.sh.
#
#   powershell -ExecutionPolicy Bypass -File scripts/install-health-task.ps1 `
#     -HealthUrl http://127.0.0.1:3100/login `
#     -AlertWebhookUrl https://hooks.slack.com/services/...
#
# Without -AlertWebhookUrl the check is LOCAL ONLY: a failure is written to the
# log and reflected in the task's Last Result, but no human is paged. That is an
# honest WARN, not an alert. Pass a Slack/Teams/Discord-compatible webhook to
# make a failure reach a person.
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
$command = "cd '$posixApp' && HEALTH_URL='$HealthUrl' ALERT_WEBHOOK_URL='$AlertWebhookUrl' ./scripts/health-watch.sh"
@(
  "@echo off",
  "echo [%DATE% %TIME%] >> `"$logPath`"",
  "`"$bash`" -lc `"$command`" >> `"$logPath`" 2>&1"
) | Set-Content -Path $wrapper -Encoding ASCII

$task = "BlackEclipse Health"
& schtasks.exe /Create /F /SC MINUTE /MO $IntervalMinutes /TN $task /TR "`"$wrapper`"" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks /Create failed (exit $LASTEXITCODE)" }
Write-Host "installed '$task' every $IntervalMinutes minute(s)"
Write-Host "health URL: $HealthUrl"
Write-Host "alert webhook: $(if ($AlertWebhookUrl) { 'configured' } else { 'NONE (local log only)' })"
Write-Host "log: $logPath"
Write-Host "run it once now: schtasks /Run /TN `"$task`""
