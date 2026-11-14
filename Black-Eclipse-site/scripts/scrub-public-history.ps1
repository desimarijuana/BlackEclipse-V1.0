# Scrub the public history into a NEW mirror. Never touches the live clone.
#
# WHY: `jdds.db` was committed before it became untracked. A public clone would
# contain every old snapshot, and one of them holds a real trading journal. This
# script clones a mirror, removes the database paths from every commit, and
# prints the verification. Pushing is deliberately a separate, explicit step.
#
# Requires git-filter-repo:  pip install git-filter-repo
#
# Usage:
#   pwsh -File scripts/scrub-public-history.ps1 -SourceUrl <private-clone-url>
#   pwsh -File scripts/scrub-public-history.ps1 -SourceUrl ... -Replacements .\replacements.txt
#
# The replacements file is the same format git-filter-repo expects:
#   old-text==>new-text        (one per line; keep it OUTSIDE the repository)
param(
  [Parameter(Mandatory = $true)]
  [string]$SourceUrl,
  [string]$WorkDir = (Join-Path $env:TEMP "blackeclipse-public-history"),
  [string]$Replacements = "",
  [string]$Mailmap = "",
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Step($message) { Write-Host "`n==> $message" -ForegroundColor Cyan }
function Fail($message) { Write-Host "FAIL: $message" -ForegroundColor Red; exit 1 }

Step "Checking git-filter-repo"
# `pip install --user` on Windows installs the launcher outside PATH; add it for
# this process so `git filter-repo` resolves as a git external command.
$userScripts = Join-Path $env:APPDATA "Python\Python312\Scripts"
if ((Test-Path (Join-Path $userScripts "git-filter-repo.exe")) -and
    -not (Get-Command git-filter-repo -ErrorAction SilentlyContinue)) {
  $env:PATH = "$userScripts;$env:PATH"
}
try {
  git filter-repo --version | Out-Null
} catch {
  Fail "git-filter-repo is not installed. Run: python -m pip install --user git-filter-repo"
}

if (Test-Path $WorkDir) {
  if (-not $Force) {
    Fail "work directory already exists: $WorkDir (pass -Force to replace it)"
  }
  Remove-Item -Recurse -Force $WorkDir
}

Step "Cloning a mirror to $WorkDir"
# --no-local keeps a local-path source packed, which is what filter-repo expects.
git clone --mirror --no-local $SourceUrl $WorkDir
if ($LASTEXITCODE -ne 0) { Fail "git clone --mirror failed" }

$dbPaths = @(
  "Black-Eclipse-site/jdds.db",
  "Black-Eclipse-site/eclipse-memory.db",
  "Black-Eclipse-site/agent-memory.db"
)
$filterArgs = @("filter-repo", "--force", "--invert-paths")
foreach ($p in $dbPaths) { $filterArgs += @("--path", $p) }
$filterArgs += @("--path-glob", "Black-Eclipse-site/*.db")
$filterArgs += @("--path-glob", "Black-Eclipse-site/*.db-wal")
$filterArgs += @("--path-glob", "Black-Eclipse-site/*.db-shm")

Step "Removing database snapshots from every commit"
git -C $WorkDir @filterArgs
if ($LASTEXITCODE -ne 0) { Fail "git filter-repo (paths) failed" }

if ($Replacements) {
  if (-not (Test-Path $Replacements)) { Fail "replacements file not found: $Replacements" }
  Step "Applying text replacements from $Replacements"
  git -C $WorkDir filter-repo --force --replace-text $Replacements
  if ($LASTEXITCODE -ne 0) { Fail "git filter-repo (replace-text) failed" }
}

if ($Mailmap) {
  if (-not (Test-Path $Mailmap)) { Fail "mailmap file not found: $Mailmap" }
  Step "Rewriting author/committer identities from $Mailmap"
  git -C $WorkDir filter-repo --force --mailmap $Mailmap
  if ($LASTEXITCODE -ne 0) { Fail "git filter-repo (mailmap) failed" }
}

Step "Verifying the rewritten history"
$dbLeft = git -C $WorkDir log --all --oneline -- "*jdds.db" "*eclipse-memory.db" "*agent-memory.db"
if ($dbLeft) {
  Fail "database paths still appear in history:`n$dbLeft"
}

Write-Host "`nLargest objects remaining (watch for multi-MB .db blobs):" -ForegroundColor Yellow
git -C $WorkDir rev-list --objects --all |
  git -C $WorkDir cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' |
  Where-Object { $_ -match '^blob' } |
  Sort-Object { [int](($_ -split ' ')[2]) } -Descending |
  Select-Object -First 10

Write-Host @"

The rewritten mirror is at:
  $WorkDir

It is NOT pushed. Next, deliberately:
  1. Create the new public repository.
  2. git -C "$WorkDir" remote add public <public-repo-url>
  3. git -C "$WorkDir" push --mirror public
  4. Re-create annotated tags on the rewritten commits.
  5. Run the credential scan over history (gitleaks/trufflehog).
  6. Run "npm run check:oss" in the public clone; it must exit 0.

The old private clone keeps its history. Do not delete it: it is the provenance
record.
"@ -ForegroundColor Green

exit 0
