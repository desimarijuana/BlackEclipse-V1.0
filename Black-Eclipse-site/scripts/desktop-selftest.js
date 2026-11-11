#!/usr/bin/env node
// Prove the desktop notification chain end to end.
//
// Launches the release shell with BE_DESKTOP_DIAGNOSTICS=1. Six seconds after the
// window navigates to the app, the shell injects a probe into the *app origin*
// that reads `typeof Notification`, `Notification.permission`, the secure-context
// flag, and dispatches one real toast. Results land in the shell log as `[diag]`.
//
// What a pass looks like:
//   [diag] {"hasNotification":true,"permission":"granted","secure":true,...}
//   [notify] sent: Black Eclipse
//
// `hasNotification:false` means the init script did not install the shim (the
// app would report "notifications unsupported"). `[notify] failed: …` means the
// OS refused the toast — on Windows that is usually Focus Assist or a disabled
// notification permission for the app.
//
// This is a diagnostic, not a launch path: it opens a real window and shows a
// toast. Nothing in normal use sets BE_DESKTOP_DIAGNOSTICS.

const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const EXE =
  process.env.BE_DESKTOP_EXE ||
  path.join(ROOT, "desktop", "src-tauri", "target", "release", "black-eclipse-desktop.exe");
const LOG = path.join(ROOT, ".black-eclipse", "desktop-native.log");

if (!fs.existsSync(EXE)) {
  console.error("Build the shell first: npm run desktop:build");
  process.exit(1);
}

try {
  fs.unlinkSync(LOG);
} catch {}

console.log("Launching with diagnostics enabled. A toast should appear.\n");

const child = spawn(EXE, [], {
  env: { ...process.env, BE_DESKTOP_DIAGNOSTICS: "1" },
  detached: true,
  stdio: "ignore",
});
child.unref();

let printed = 0;
const started = Date.now();

const timer = setInterval(() => {
  let text = "";
  try {
    text = fs.readFileSync(LOG, "utf8");
  } catch {}
  const lines = text.split("\n").filter((l) => l.includes("[diag]") || l.includes("[notify]"));
  for (; printed < lines.length; printed += 1) {
    console.log(lines[printed]);
  }

  const report = lines.find((l) => l.includes("[diag] hn:"));
  if (report) {
    clearInterval(timer);
    const get = (key) => {
      const m = new RegExp(key + ":([^~]*)").exec(report);
      return m ? m[1] : "?";
    };
    console.log("");
    console.log("  Notification defined (hn):      ", get("hn") === "1" ? "YES" : "NO");
    console.log("  Constructor name (ctor):        ", get("ctor"));
    console.log("  Permission:                     ", get("perm"));
    console.log("  Secure context:                 ", get("sec") === "1" ? "YES" : "NO");
    console.log("  Tauri IPC (tauri):              ", get("tauri") === "1" ? "YES" : "NO");
    console.log("  Shim call (shimcall):           ", get("shimcall"));
    console.log("  Direct emit (direct):           ", get("direct"));
    const ok =
      get("hn") === "1" &&
      get("direct") === "ok" &&
      get("shimcall") === "dispatched";
    console.log(ok ? "\nPASS — the OS toast path works end to end." : "\nFAIL — see the values above.");
    console.log("The window stays open; close it from the tray.");
    process.exit(ok ? 0 : 1);
  }

  if (Date.now() - started > 45_000) {
    clearInterval(timer);
    console.error("Timed out without a diagnostic report. See " + LOG);
    process.exit(2);
  }
}, 800);
