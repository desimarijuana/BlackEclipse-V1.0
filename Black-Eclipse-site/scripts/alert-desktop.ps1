# Show a Windows desktop notification for a BlackEclipse alert.
#
# This is the local escalation used when no ALERT_WEBHOOK_URL is configured.
# It reaches the signed-in operator on the machine running the health task; it
# is NOT a remote page. Use a webhook for an off-machine human channel.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/alert-desktop.ps1 `
#     -Message "BlackEclipse is unhealthy: /login -> 000"
#
# Exit 0 = the notification was shown. No admin rights are required.
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$Message,
  [string]$Title = "BlackEclipse health",
  [int]$Seconds = 15
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$icon = $null
try {
  $icon = New-Object System.Windows.Forms.NotifyIcon
  $icon.Icon = [System.Drawing.SystemIcons]::Warning
  $icon.Visible = $true
  $icon.BalloonTipTitle = $Title
  $icon.BalloonTipText = $Message
  $icon.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Warning
  $icon.ShowBalloonTip([Math]::Max($Seconds, 5) * 1000)
  Start-Sleep -Seconds 2
} finally {
  if ($icon) { $icon.Dispose() }
}
