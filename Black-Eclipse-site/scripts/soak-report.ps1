# Summarise the BlackEclipse soak evidence from the health-watch log.
#
# The soak exit gate is "one full week of a live instance with no silent
# failure". This script turns the log the health task already writes into the
# evidence for that gate: samples, failures, uptime, coverage gaps and the
# ALERT-ACTIVE marker.
#
#   powershell -ExecutionPolicy Bypass -File scripts/soak-report.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/soak-report.ps1 -Days 7
#
# Exit 0 = the window is covered with no recorded failure. Exit 1 = a failure or
# a coverage gap (a stopped task is itself a silent failure). Exit 2 = no log.
[CmdletBinding()]
param(
  [string]$LogPath = (Join-Path $env:LOCALAPPDATA "BlackEclipse\health.log"),
  [int]$Days = 7,
  [int]$MaxGapMinutes = 10
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $LogPath)) {
  Write-Error "no health log at $LogPath"
  exit 2
}

$lines = Get-Content $LogPath
$stampRe = '^\[(?<stamp>[^\]]+)\]'
$samples = New-Object System.Collections.Generic.List[datetime]
$healthy = 0
$failed = 0
$current = $null
$failures = New-Object System.Collections.Generic.List[string]

foreach ($line in $lines) {
  $m = [regex]::Match($line, $stampRe)
  if ($m.Success) {
    if ($current) {
      if ($current.text -match '^\s*healthy:') { $healthy++ }
      elseif ($current.text -match 'ALERT:|health check FAILED|alert delivery FAILED') {
        $failed++
        $failures.Add("$($current.stamp) $($current.text.Trim())")
      }
    }
    $stamp = $m.Groups['stamp'].Value
    $parsed = [datetime]::MinValue
    if ([datetime]::TryParse($stamp, [ref]$parsed)) { $samples.Add($parsed) }
    $current = [pscustomobject]@{ stamp = $stamp; time = $parsed; text = "" }
  } elseif ($current) {
    $current.text += "$line`n"
  }
}
if ($current) {
  if ($current.text -match '^\s*healthy:') { $healthy++ }
  elseif ($current.text -match 'ALERT:|health check FAILED|alert delivery FAILED') {
    $failed++
    $failures.Add("$($current.stamp) $($current.text.Trim())")
  }
}

if ($samples.Count -eq 0) { Write-Error "no timestamped samples in $LogPath"; exit 2 }

$first = ($samples | Measure-Object -Minimum).Minimum
$last = ($samples | Measure-Object -Maximum).Maximum
$windowEnd = (Get-Date)
$span = $last - $first
$expected = [Math]::Max(1, [int][Math]::Floor($span.TotalMinutes / 5) + 1)

$gaps = @()
for ($i = 1; $i -lt $samples.Count; $i++) {
  $delta = ($samples[$i] - $samples[$i - 1]).TotalMinutes
  if ($delta -gt $MaxGapMinutes) {
    $gaps += "{0:yyyy-MM-dd HH:mm} -> {1:yyyy-MM-dd HH:mm} ({2:N0} min)" -f $samples[$i - 1], $samples[$i], $delta
  }
}
$tailGap = ($windowEnd - $last).TotalMinutes
$marker = Join-Path (Split-Path $LogPath) "ALERT-ACTIVE.txt"

$uptime = if ($healthy + $failed -gt 0) { 100.0 * $healthy / ($healthy + $failed) } else { 0 }

Write-Host "BlackEclipse soak report"
Write-Host "  log:        $LogPath"
Write-Host "  window:     $($first.ToString('yyyy-MM-dd HH:mm')) -> $($last.ToString('yyyy-MM-dd HH:mm')) ($([Math]::Round($span.TotalHours,1)) h)"
Write-Host "  samples:    $($samples.Count) (expected about $expected at 5-minute cadence)"
Write-Host "  healthy:    $healthy"
Write-Host "  failed:     $failed"
Write-Host "  uptime:     $([Math]::Round($uptime,2)) %"
Write-Host "  since last: $([Math]::Round($tailGap,0)) min"
Write-Host "  alert marker present: $(Test-Path $marker)"
if ($gaps.Count -gt 0) {
  Write-Host "  coverage gaps (> $MaxGapMinutes min):"
  $gaps | ForEach-Object { Write-Host "    $_" }
}
if ($failures.Count -gt 0) {
  Write-Host "  recorded failures:"
  $failures | Select-Object -Last 10 | ForEach-Object { Write-Host "    $_" }
}

$required = [datetime]::UtcNow.AddDays(-$Days)
$covered = $first -le $required
if ($Days -gt 0 -and -not $covered) {
  Write-Host "  soak: INCOMPLETE - first sample is $([Math]::Round(($windowEnd - $first).TotalHours,1)) h old; $Days days required"
}
if ($failed -gt 0 -or $gaps.Count -gt 0 -or $tailGap -gt $MaxGapMinutes) { exit 1 }
if ($Days -gt 0 -and -not $covered) { exit 1 }
Write-Host "  soak: PASS"
exit 0
