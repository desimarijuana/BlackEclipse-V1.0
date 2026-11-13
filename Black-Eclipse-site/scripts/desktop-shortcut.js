#!/usr/bin/env node
// Install / repair the Windows "Black Eclipse" desktop shortcut.
//
// Why this exists
// ---------------
// The desktop launcher is `start-eclipse.vbs`, so the old shortcut pointed at
// `wscript.exe`. Windows 11's modern right-click menu draws the *target's*
// icon for the "Open" row, not the shortcut's `IconLocation` — so the menu
// showed the colourful Windows Script Host icon while the desktop tile showed
// the Eclipse mark. Setting `IconLocation` alone can never fix that row.
//
// The fix is to give the shortcut a target that actually owns the app icon:
// a tiny generated `Black Eclipse.exe` (compiled with the .NET Framework `csc`
// that ships with Windows) that starts the same VBS launcher, with
// `public/branding/black-eclipse.ico` embedded as its icon. The shortcut then
// shows the Eclipse mark on the desktop, in Start, in the context menu, the
// taskbar, and Alt-Tab.
//
// Nothing is downloaded and no dependency is added: `csc.exe` is part of
// Windows, and the generated launcher + shortcut live in `.black-eclipse/`
// (gitignored) and on the user's Desktop. Re-run this after the icon changes.

const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const RUNTIME_DIR = path.join(ROOT, ".black-eclipse");
const LAUNCHER_EXE = path.join(RUNTIME_DIR, "Black Eclipse.exe");
const LAUNCHER_CS = path.join(RUNTIME_DIR, "Black Eclipse.cs");
const APP_ICON = path.join(ROOT, "public", "branding", "black-eclipse.ico");
const SHORTCUT_NAME = "Black Eclipse.lnk";

const LAUNCHER_SOURCE = `using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;

// Tiny icon-carrying shim: starts the real launcher (start-eclipse.vbs) with
// no console window, and reports a missing Node/VBS through the VBS itself.
internal static class Program
{
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);

    [STAThread]
    private static int Main()
    {
        string root = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, ".."));
        string launcher = Path.Combine(root, "start-eclipse.vbs");
        if (!File.Exists(launcher))
        {
            MessageBoxW(IntPtr.Zero,
                "Black Eclipse could not find start-eclipse.vbs in:\\n\\n" + root,
                "Black Eclipse", 0x10);
            return 1;
        }

        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = Path.Combine(Environment.SystemDirectory, "wscript.exe"),
                Arguments = "\\"" + launcher + "\\"",
                WorkingDirectory = root,
                UseShellExecute = true
            });
            return 0;
        }
        catch (Exception ex)
        {
            MessageBoxW(IntPtr.Zero,
                "Black Eclipse could not start its launcher.\\n\\n" + ex.Message,
                "Black Eclipse", 0x10);
            return 1;
        }
    }
}
`;

function log(msg) {
  console.log(`[desktop] ${msg}`);
}

function findCsc() {
  const windir = process.env.WINDIR || process.env.SystemRoot;
  if (!windir) return null;
  for (const framework of ["Framework64", "Framework"]) {
    const candidate = path.join(windir, "Microsoft.NET", framework, "v4.0.30319", "csc.exe");
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function mtime(file) {
  try {
    return fs.statSync(file).mtimeMs;
  } catch {
    return 0;
  }
}

function ensureLauncher() {
  if (!fs.existsSync(APP_ICON)) {
    throw new Error(`app icon not found: ${APP_ICON}`);
  }

  fs.mkdirSync(RUNTIME_DIR, { recursive: true });
  fs.writeFileSync(LAUNCHER_CS, LAUNCHER_SOURCE, "utf8");

  // Rebuild when the exe is missing or older than the icon it embeds (or than
  // this script, whose C# source lives above).
  const exeTime = mtime(LAUNCHER_EXE);
  const stale = exeTime === 0 || mtime(APP_ICON) > exeTime || mtime(path.resolve(__filename)) > exeTime;
  if (!stale) {
    log(`launcher up to date: ${path.relative(ROOT, LAUNCHER_EXE)}`);
    return;
  }

  const csc = findCsc();
  if (!csc) {
    throw new Error("the .NET Framework C# compiler (csc.exe) was not found — cannot build the icon launcher");
  }

  log("building icon launcher...");
  const result = spawnSync(
    csc,
    [
      "/nologo",
      "/target:winexe",
      "/platform:anycpu",
      "/optimize+",
      `/win32icon:${APP_ICON}`,
      `/out:${LAUNCHER_EXE}`,
      LAUNCHER_CS,
    ],
    { stdio: "inherit" }
  );
  if (result.status !== 0 || !fs.existsSync(LAUNCHER_EXE)) {
    throw new Error("csc failed to build the launcher");
  }
  log(`built ${path.relative(ROOT, LAUNCHER_EXE)}`);
}

function installShortcut() {
  const ps = `
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop $env:BE_SHORTCUT_NAME
if (-not (Test-Path -LiteralPath $lnk)) {
  # Repair an existing shortcut (any name) that pointed at start-eclipse.vbs
  # or at an older copy of the generated launcher.
  $found = Get-ChildItem -LiteralPath $desktop -Filter *.lnk -ErrorAction SilentlyContinue | Where-Object {
    $s = $shell.CreateShortcut($_.FullName)
    (($s.TargetPath -like '*wscript.exe') -and ($s.Arguments -like '*start-eclipse.vbs*')) -or
      ($s.TargetPath -like '*Black Eclipse.exe')
  } | Select-Object -First 1
  if ($found) { $lnk = $found.FullName }
}
$shortcut = $shell.CreateShortcut($lnk)
# Desktop-first: when the native app is installed, the icon opens IT, not the
# retired browser launcher. The generated shim stays as a fallback for a
# checkout that has no install yet.
$target = $env:BE_LAUNCHER_EXE
$workdir = $env:BE_ROOT
if ($env:BE_TAURI_EXE -and (Test-Path -LiteralPath $env:BE_TAURI_EXE)) {
  $target = $env:BE_TAURI_EXE
  $workdir = Split-Path -Parent $target
}
$shortcut.TargetPath = $target
$shortcut.Arguments = ''
$shortcut.WorkingDirectory = $workdir
$shortcut.IconLocation = "$target,0"
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
        BE_LAUNCHER_EXE: LAUNCHER_EXE,
        BE_ROOT: ROOT,
        BE_TAURI_EXE: path.join(
          process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"),
          "Programs",
          "BlackEclipse",
          "Black Eclipse.exe",
        ),
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

// Windows caches shell icons per (path, index). A regenerated exe at the same
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
  ensureLauncher();
  installShortcut();
  refreshIconCache();
}

try {
  main();
} catch (err) {
  console.error(`[desktop] ${err.message}`);
  process.exit(1);
}
