# Install a daily BlackEclipse data backup as a Windows Task Scheduler task.
# The Linux equivalent is scripts/install-backup-timer.sh (systemd timer).
#
#   powershell -ExecutionPolicy Bypass -File scripts/install-backup-task.ps1
#   ... -Time 02:30 -Keep 30 -OutDir D:\backups\blackeclipse
#
# It wraps the SAME scripts/backup.sh (SQLite backup API + integrity check +
# retention) in a tiny .cmd, resolves the bash on this machine, and registers a
# user-level daily task. Run the task once after installing to verify.
[CmdletBinding()]
param(
  [string]$Time = "03:15",
  [int]$Keep = 14,
  [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$app = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$bash = (Get-Command bash -ErrorAction Stop).Source
if (-not $OutDir) { $OutDir = Join-Path $app "backups" }
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

$winApp = $app -replace "\\", "/"
$winOut = $OutDir -replace "\\", "/"
$posixApp = (& $bash -lc "cygpath -u '$winApp'").Trim()
$posixOut = (& $bash -lc "cygpath -u '$winOut'").Trim()
if (-not $posixApp -or -not $posixOut) { throw "cygpath could not resolve the paths" }

# The wrapper must live on a SPACE-FREE path: schtasks stores `/TR` unquoted,
# so a path containing "Default Project" is split and the task fails 0x80070002.
# The app path itself is quoted INSIDE the wrapper's bash command.
$wrapperDir = Join-Path $env:LOCALAPPDATA "BlackEclipse"
New-Item -ItemType Directory -Path $wrapperDir -Force | Out-Null
$wrapper = Join-Path $wrapperDir "backup-task.cmd"
$command = "cd '$posixApp' && BE_BACKUP_DIR='$posixOut' BE_BACKUP_KEEP=$Keep ./scripts/backup.sh --data-dir . --out '$posixOut' --keep $Keep"
@(
  "@echo off",
  "`"$bash`" -lc `"$command`""
) | Set-Content -Path $wrapper -Encoding ASCII

$task = "BlackEclipse Backup"
& schtasks.exe /Create /F /SC DAILY /ST $Time /TN $task /TR "`"$wrapper`"" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks /Create failed (exit $LASTEXITCODE)" }
Write-Host "installed '$task' daily at $Time"
Write-Host "wrapper: $wrapper"
Write-Host "run it once now: schtasks /Run /TN `"$task`""
