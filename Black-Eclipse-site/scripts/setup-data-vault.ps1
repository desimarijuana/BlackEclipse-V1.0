# setup-data-vault.ps1
#
# Moves every piece of BlackEclipse personal data onto an encrypted volume so it
# is unreadable while the volume is locked (and at rest on a stolen disk).
#
# WHAT MOVES (the app keeps working - it reads BE_DATA_DIR / the junctions):
#   jdds.db, agent-memory.db, eclipse-memory.db (+ WAL/SHM sidecars)
#   .black-eclipse/            (auth.db, conversations, artifacts, documents,
#                               browser profiles, computer-use recordings, skills)
#   python/.black-eclipse/     (channel gateway secret)
#   backups/, _backups/        (rolling + manual database copies)
#   mcp-servers.json, .connector-key
#
# WHAT DOES NOT MOVE: source code, node_modules, .env. Keep a copy of .env's
# secrets in your password manager; the file itself stays in the repo (gitignored).
#
# USAGE (elevated PowerShell - BitLocker needs admin):
#   powershell -ExecutionPolicy Bypass -File scripts/setup-data-vault.ps1 -DryRun
#   powershell -ExecutionPolicy Bypass -File scripts/setup-data-vault.ps1 -Apply
#
# Already have a VeraCrypt/BitLocker volume mounted at V:?
#   ... -SkipBitLocker -Apply
#
# The volume is UNLOCKED once per boot (BitLocker password). While it is locked,
# `npm run dev` / `npm start` refuse to run instead of creating empty databases.

[CmdletBinding()]
param(
  [string]$DriveLetter = "V",
  [string]$VhdPath = "$env:USERPROFILE\BlackEclipseVault\blackeclipse-vault.vhdx",
  [int]$SizeGB = 20,
  [switch]$SkipBitLocker,
  [switch]$Apply,
  [switch]$DryRun,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$SiteRoot = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $SiteRoot
$DataDir = "${DriveLetter}:\BlackEclipseData"
$Mode = if ($DryRun -or -not $Apply) { "PLAN" } else { "APPLY" }

function Write-Step($msg) { Write-Host "  $msg" }
function Fail($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

# -- 0. Safety checks --------------------------------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($Mode -eq "APPLY" -and -not $isAdmin) {
  Fail "BitLocker and moving data need an elevated PowerShell (Run as Administrator)."
}
if ($Mode -eq "APPLY") {
  $listeners = @(3000, 3100, 8765, 8766 | Where-Object {
      (Get-NetTCPConnection -State Listen -LocalPort $_ -ErrorAction SilentlyContinue)
    })
  if ($listeners.Count -gt 0 -and -not $Force) {
    Fail ("BlackEclipse looks like it is running (listening on: " + ($listeners -join ", ") +
      "). Stop it first, or pass -Force if you are certain the databases are idle.")
  }
}

Write-Host "`nBlackEclipse data vault ($Mode)" -ForegroundColor Cyan
Write-Step "volume:     ${DriveLetter}: ($VhdPath)"
Write-Step "data dir:   $DataDir"
Write-Step "site root:  $SiteRoot"
Write-Host ""

# -- 1. Create + mount + encrypt the volume (skipped for an existing one) ----
$volumeReady = Test-Path "${DriveLetter}:\"
if (-not $volumeReady) {
  if ($SkipBitLocker) {
    Fail "${DriveLetter}: is not mounted. Mount your encrypted volume first, then rerun."
  }
  $hasHyperV = [bool](Get-Command New-VHD -ErrorAction SilentlyContinue)
  $hasBitLocker = [bool](Get-Command Enable-BitLocker -ErrorAction SilentlyContinue)
  if (-not $hasBitLocker) {
    Fail @"
BitLocker cmdlets (Enable-BitLocker) are not available on this Windows edition,
so this script cannot encrypt the disk for you. Create an encrypted VeraCrypt
volume, mount it as ${DriveLetter}:, then rerun with:
  -SkipBitLocker -Apply
"@
  }
  if ($Mode -eq "PLAN") {
    $maker = if ($hasHyperV) { "New-VHD" } else { "diskpart" }
    Write-Step "[plan] create ${SizeGB}GB dynamic VHDX via $maker, format NTFS, assign ${DriveLetter}:"
    Write-Step "[plan] enable BitLocker (XtsAes256, used-space-only) with a password"
    Write-Step "[plan] move personal data + write BE_DATA_DIR / BE_VAULT_PATH"
  } else {
    Write-Host "Creating the virtual disk..." -ForegroundColor Yellow
    $vhdDir = Split-Path -Parent $VhdPath
    if (-not (Test-Path $vhdDir)) { New-Item -ItemType Directory -Path $vhdDir -Force | Out-Null }

    if ($hasHyperV) {
      if (-not (Test-Path $VhdPath)) {
        New-VHD -Path $VhdPath -SizeBytes ($SizeGB * 1GB) -Dynamic | Out-Null
      }
      Mount-VHD -Path $VhdPath | Out-Null
      $disk = Get-Disk | Where-Object { $_.Location -like "*$([IO.Path]::GetFileName($VhdPath))*" } | Select-Object -First 1
      if (-not $disk) { Fail "Could not find the mounted VHD disk." }
      if ($disk.PartitionStyle -eq "RAW") { Initialize-Disk -Number $disk.Number -PartitionStyle GPT | Out-Null }
      $part = Get-Partition -DiskNumber $disk.Number -ErrorAction SilentlyContinue | Select-Object -First 1
      if (-not $part) {
        $part = New-Partition -DiskNumber $disk.Number -UseMaximumSize -DriveLetter $DriveLetter
      } elseif ($part.DriveLetter -ne $DriveLetter[0]) {
        Set-Partition -DiskNumber $disk.Number -PartitionNumber $part.PartitionNumber -NewDriveLetter $DriveLetter
      }
      Start-Sleep -Seconds 1
      if (-not (Get-Volume -DriveLetter $DriveLetter -ErrorAction SilentlyContinue)) {
        Format-Volume -DriveLetter $DriveLetter -FileSystem NTFS -NewFileSystemLabel "BlackEclipseVault" -Confirm:$false | Out-Null
      }
    } else {
      # No Hyper-V module (common on Windows Home / stripped Pro installs).
      # diskpart can still create and attach a VHDX; only the ENCRYPTION needs
      # BitLocker, which is checked above.
      if (Test-Path $VhdPath) {
        Fail "The VHDX already exists but is not attached. Attach it manually, or mount your encrypted volume and rerun with -SkipBitLocker -Apply."
      }
      $sizeMB = $SizeGB * 1024
      $dp = @"
create vdisk file="$VhdPath" maximum=$sizeMB type=expandable
select vdisk file="$VhdPath"
attach vdisk
create partition primary
format fs=ntfs quick label=BlackEclipseVault
assign letter=$DriveLetter
"@
      $dpFile = Join-Path $env:TEMP "be-vault-diskpart.txt"
      Set-Content -Path $dpFile -Value $dp -Encoding ascii
      $dpOut = diskpart /s $dpFile
      if ($LASTEXITCODE -ne 0) { Fail "diskpart failed:`n$dpOut" }
      Start-Sleep -Seconds 2
    }

    Write-Host "Enabling BitLocker (you will set a password)..." -ForegroundColor Yellow
    $secure = Read-Host -AsSecureString "BitLocker password for ${DriveLetter}:"
    Enable-BitLocker -MountPoint "${DriveLetter}:" -EncryptionMethod XtsAes256 `
      -UsedSpaceOnly -PasswordProtector -Password $secure | Out-Null
    Add-BitLockerKeyProtector -MountPoint "${DriveLetter}:" -RecoveryPasswordProtector | Out-Null
    $recovery = (Get-BitLockerVolume -MountPoint "${DriveLetter}:").KeyProtector |
      Where-Object { $_.KeyProtectorType -eq "RecoveryPassword" } |
      Select-Object -First 1
    if ($recovery) {
      $recoveryFile = Join-Path (Split-Path -Parent $VhdPath) "RECOVERY-KEY.txt"
      "BitLocker recovery key for ${DriveLetter}: $($recovery.RecoveryPassword)" |
        Set-Content -Path $recoveryFile -Encoding ascii
      Write-Host "  Recovery key saved to: $recoveryFile  (store it OFF this machine)" -ForegroundColor Yellow
    }
    $volumeReady = $true
  }
} else {
  Write-Step "${DriveLetter}: is already mounted - using it as-is."
}

if (-not (Test-Path $DataDir) -and $Mode -eq "APPLY") {
  New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
}

# -- 2. Move data and leave links --------------------------------------------
# Directories become junctions (no admin needed at runtime). Database files are
# NOT linked: the app reads them through BE_DATA_DIR, so SQLite's -wal/-shm
# sidecars are created on the encrypted volume too (a file symlink would leave
# the newest transactions next to the link, unencrypted).
$dirTargets = @(
  @{ Path = (Join-Path $SiteRoot ".black-eclipse"); Name = ".black-eclipse" },
  @{ Path = (Join-Path $SiteRoot "python\.black-eclipse"); Name = "python-black-eclipse" },
  @{ Path = (Join-Path $SiteRoot "backups"); Name = "backups" },
  @{ Path = (Join-Path $RepoRoot "_backups"); Name = "_backups" }
)
$fileTargets = @(
  @{ Path = (Join-Path $RepoRoot "mcp-servers.json"); Name = "mcp-servers.json" },
  @{ Path = (Join-Path $SiteRoot "mcp-servers.json"); Name = "site-mcp-servers.json" },
  @{ Path = (Join-Path $SiteRoot ".connector-key"); Name = "connector-key" }
)
$dbFiles = @("jdds.db", "agent-memory.db", "eclipse-memory.db") | ForEach-Object {
  @{ Path = (Join-Path $SiteRoot $_); Name = $_ }
}

function Move-One($item, $isDir) {
  $src = $item.Path
  $linkType = if (Test-Path $src) { (Get-Item $src -Force).LinkType } else { $null }
  if ($linkType) {
    Write-Step "skip (already a link): $src"
    return
  }
  $dest = [IO.Path]::Combine($DataDir, $item.Name)
  if (-not (Test-Path $src)) {
    # Nothing to move yet, but the runtime will create it on first use. Point the
    # empty location at the vault now so it lands encrypted from the first write.
    if (-not $isDir) { return }
    if ($Mode -eq "PLAN") { Write-Step "[plan] create empty $dest; junction $src -> $dest"; return }
    if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
    New-Item -ItemType Junction -Path $src -Target $dest | Out-Null
    Write-Step "linked (new) $($item.Name)"
    return
  }
  if ($Mode -eq "PLAN") {
    Write-Step "[plan] move $src -> $dest; link back"
    return
  }
  if (Test-Path $dest) {
    Fail "Destination already exists: $dest. Move it aside or rerun with the data already on the vault."
  }
  Move-Item -LiteralPath $src -Destination $dest
  if ($isDir) {
    New-Item -ItemType Junction -Path $src -Target $dest | Out-Null
  } else {
    New-Item -ItemType SymbolicLink -Path $src -Target $dest | Out-Null
  }
  Write-Step "moved $($item.Name)"
}

foreach ($t in $dirTargets) { Move-One $t $true }
foreach ($t in $fileTargets) { Move-One $t $false }

# Databases: move the file and its sidecars. No link is created - BE_DATA_DIR is
# the single source of truth. If an older tool insists on the repo path, it will
# create a NEW empty file; do not run such a tool against a vaulted install.
foreach ($t in $dbFiles) {
  $src = $t.Path
  if (-not (Test-Path $src)) { continue }
  if ((Get-Item $src -Force).LinkType) { Write-Step "skip (already a link): $src"; continue }
  $dest = [IO.Path]::Combine($DataDir, $t.Name)
  if ($Mode -eq "PLAN") { Write-Step "[plan] move $src (+ sidecars) -> $dest"; continue }
  if (Test-Path $dest) { Fail "Destination already exists: $dest." }
  Move-Item -LiteralPath $src -Destination $dest
  foreach ($suffix in @("-wal", "-shm", "-journal")) {
    $side = "$src$suffix"
    if (Test-Path $side) {
      Move-Item -LiteralPath $side -Destination "$dest$suffix"
    }
  }
  Write-Step "moved $($t.Name) (+ sidecars)"
}

# -- 3. Record the configuration ---------------------------------------------
$envPath = Join-Path $SiteRoot ".env"
function Set-EnvValue([string]$key, [string]$value) {
  if ($Mode -eq "PLAN") { Write-Step "[plan] .env $key=$value"; return }
  $lines = @()
  if (Test-Path $envPath) { $lines = Get-Content -LiteralPath $envPath }
  $found = $false
  $out = foreach ($line in $lines) {
    if ($line -match "^\s*$([regex]::Escape($key))\s*=") {
      $found = $true
      "$key=$value"
    } else { $line }
  }
  if (-not $found) { $out += "$key=$value" }
  [IO.File]::WriteAllLines($envPath, [string[]]$out)
}
Set-EnvValue "BE_DATA_DIR" $DataDir
Set-EnvValue "BE_VAULT_PATH" $DataDir

# -- 4. Done -----------------------------------------------------------------
if ($Mode -eq "PLAN") {
  Write-Host "`nPlan only - nothing was changed. Re-run with -Apply to execute.`n" -ForegroundColor Cyan
  exit 0
}

Write-Host "`nDone. Your personal data now lives on ${DriveLetter}: (encrypted)." -ForegroundColor Green
Write-Host @"
Unlock it after every reboot: enter the BitLocker password for ${DriveLetter}: in
Explorer, or run:  Manage-bde -unlock ${DriveLetter}: -RecoveryPassword <key>

Then start the app normally:
  cd "$SiteRoot"
  npm run up

If ${DriveLetter}: is locked, the start will STOP with a clear message rather than
create empty databases. Keep the recovery key somewhere other than this machine.
"@
