// ── Native Windows folder dialog ────────────────────────────────────────────
//
// The in-app picker is the fallback; this opens the real Windows "Select Folder"
// dialog from the machine that runs the app. It is server-side because a browser
// directory handle never exposes an absolute path the Python runtime could use.
//
// The call BLOCKS until the person picks or cancels, so the route gives it a
// generous timeout. A headless/remote server has no desktop: the dialog cannot
// appear, the timeout fires, and the caller falls back to the in-app picker.
//
// Server-only.

import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

// A tiny always-on-top owner form keeps the dialog in front of the app. It is
// not shown in the taskbar, has no border, and closes right after the dialog.
const PS_SCRIPT = String.raw`
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$owner.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$owner.Size = New-Object System.Drawing.Size(1, 1)
$owner.Show()
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Choose a folder for Eclipse'
$dialog.ShowNewFolderButton = $true
$result = $dialog.ShowDialog($owner)
$owner.Close()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
  [Console]::Out.Write($dialog.SelectedPath)
}
`;

/** Open the Windows folder dialog. Returns the chosen path, or null if cancelled. */
export async function pickNativeFolder(): Promise<string | null> {
  if (process.platform !== "win32") {
    throw new Error("The native folder dialog is only available on Windows.");
  }
  const { stdout } = await execFileAsync(
    "powershell.exe",
    ["-NoProfile", "-STA", "-Command", PS_SCRIPT],
    { timeout: 300_000, windowsHide: true, maxBuffer: 1 << 20 },
  );
  const chosen = String(stdout ?? "").replace(/^\uFEFF/, "").trim();
  return chosen || null;
}
