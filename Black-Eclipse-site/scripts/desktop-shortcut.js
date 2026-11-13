#!/usr/bin/env node
// Install / repair the Windows "Black Eclipse" desktop shortcut.
//
// The product is the native desktop app, so the shortcut points at the
// installed `Black Eclipse.exe` and nothing else. It used to point at a
// generated shim → `start-eclipse.vbs` → the retired browser launcher, which
// meant a checkout without the native app got an icon that silently did
// nothing. That shim chain is gone: when the app is not installed this script
// fails loudly and tells you how to build it.
//
// Why the target matters beyond just launching: Windows 11's modern right-click
// menu draws the *target's* icon for the "Open" row, not the shortcut's
// `IconLocation` — so a shortcut to `wscript.exe` could never show the Eclipse
// mark there. The native exe owns the icon.
//
// Nothing is downloaded and no dependency is added. Re-run this after the
// native app is reinstalled or its icon changes.

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const { installedShellPath, devShellPath } = require("./lib/desktop-process");

const ROOT = path.resolve(__dirname, "..");
const SHORTCUT_NAME = "Black Eclipse.lnk";

function log(msg) {
  console.log(`[desktop] ${msg}`);
}

function installShortcut(exe) {
  const ps = `
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop $env:BE_SHORTCUT_NAME
if (-not (Test-Path -LiteralPath $lnk)) {
  # Repair an existing shortcut (any name) that pointed at the retired
  # wscript/VBS launcher or any older Black Eclipse target.
  $found = Get-ChildItem -LiteralPath $desktop -Filter *.lnk -ErrorAction SilentlyContinue | Where-Object {
    $s = $shell.CreateShortcut($_.FullName)
    ($s.TargetPath -like '*wscript.exe') -or
      ($s.TargetPath -like '*start-eclipse*') -or
      ($s.TargetPath -like '*Black Eclipse.exe')
  } | Select-Object -First 1
  if ($found) { $lnk = $found.FullName }
}
$shortcut = $shell.CreateShortcut($lnk)
$shortcut.TargetPath = $env:BE_TARGET
$shortcut.Arguments = ''
$shortcut.WorkingDirectory = Split-Path -Parent $env:BE_TARGET
$shortcut.IconLocation = "$env:BE_TARGET,0"
$shortcut.Description = 'Start Black Eclipse'
$shortcut.WindowStyle = 1
$shortcut.Save()
Write-Output $lnk
`;

  const result = spawnSync(
    "powershell",
    ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps],
    {
      encoding: "utf8",
      env: {
        ...process.env,
        BE_SHORTCUT_NAME: SHORTCUT_NAME,
        BE_TARGET: exe,
      },
    }
  );
  if (result.status !== 0) {
    throw new Error(`could not install the shortcut: ${(result.stderr || "").trim() || `exit ${result.status}`}`);
  }
  const lnk = (result.stdout || "").trim().split(/\r?\n/).pop();
  log(`shortcut ready: ${lnk}`);
  return lnk;
}

// Windows caches shell icons per (path, index). A reinstalled exe at the same
// path can keep showing the old bitmap in Explorer until the shell re-reads
// it, so ask the shell to refresh after every install.
function refreshIconCache() {
  spawnSync("ie4uinit.exe", ["-show"], { stdio: "ignore" });
  const ps = `
Add-Type -Namespace Win32 -Name Shell -MemberDefinition '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int eventId, uint flags, IntPtr item1, IntPtr item2);'
[Win32.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
`;
  spawnSync("powershell", ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps], {
    stdio: "ignore",
  });
}

function main() {
  if (process.platform !== "win32") {
    log("the desktop shortcut installer is Windows-only — nothing to do");
    return;
  }

  const exe = installedShellPath();
  if (!fs.existsSync(exe)) {
    throw new Error(
      [
        "the Black Eclipse desktop app is not installed, so there is nothing to point the shortcut at:",
        `  expected: ${exe}`,
        "",
        "Build the installer, then run this again:",
        "  npm run desktop:installer",
        "",
        "Or point the icon at the Dev channel shell:",
        `  ${devShellPath()}`,
      ].join("\n"),
    );
  }

  installShortcut(exe);
  refreshIconCache();
}

try {
  main();
} catch (err) {
  console.error(`[desktop] ${err.message}`);
  process.exit(1);
}
