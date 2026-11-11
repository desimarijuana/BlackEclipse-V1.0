#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! Black Eclipse — native shell.
//!
//! Scope: a WebView2 window and the lifecycle of ONE child process (the Node
//! server bootstrap in `scripts/desktop-server.js`). The Next server already
//! supervises the Python harness, so this shell deliberately knows nothing
//! about Python.
//!
//! Origin: the window loads `http://127.0.0.1:3100`. Loopback is already a
//! secure context, so notifications, camera and microphone keep working
//! without the TLS reverse proxy the browser path uses.
//!
//! The browser front door (`npm run dev`, `npm start`, `black eclipse`,
//! `start-eclipse.vbs`) is untouched by this crate.

use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{
    AppHandle, Emitter, Listener, Manager, RunEvent, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
    WindowEvent,
};

/// The production port. Must match `PROD.appPort` in `scripts/lib/profiles.js`.
const APP_PORT: u16 = 3100;

/// `BE_DESKTOP_PORT` lets a test (or an operator) move both the bootstrap and
/// the window together; without it the shell and the bootstrap could disagree.
fn app_port() -> u16 {
    std::env::var("BE_DESKTOP_PORT")
        .ok()
        .and_then(|v| v.trim().parse::<u16>().ok())
        .unwrap_or(APP_PORT)
}

/// Escapes the app's `X-Frame-Options`/CSP concerns: the splash is local
/// bundled HTML served over Tauri's own asset protocol.
const SPLASH: &str = "index.html";

/// Injected before any application script runs. WebView2 does not implement
/// the Notification API, so the app's alerts settings screen would report "not
/// supported" inside the desktop window. This maps the standard constructor onto
/// a native toast, so the existing browser-notifier code keeps working unchanged.
///
/// IMPORTANT: this talks to Rust through **events**, not `invoke`. Tauri 2 denies
/// app-defined commands to remote origins (the window loads
/// `http://127.0.0.1:3100`, which is remote as far as the ACL is concerned) —
/// `invoke('desktop_notify')` fails with "not allowed. Plugin not found". Core
/// event commands ARE permitted to a capability-listed remote origin, so
/// `be-notify` / `be-shortcut` are the transport.
const INIT_SCRIPT: &str = r#"
(function () {
  var T = window.__TAURI__;
  var emit = T && T.event && typeof T.event.emit === 'function' ? T.event.emit : null;
  // If the global API is not exposed (an older build, or a remote origin the
  // capability did not list), fall back to the raw IPC invoke. Core event
  // commands are the one surface Tauri guarantees to a capability-listed
  // remote origin, so window chrome and notifications keep working.
  if (!emit) {
    var I = window.__TAURI_INTERNALS__;
    if (I && typeof I.invoke === 'function') {
      emit = function (name, payload) {
        return I.invoke('plugin:event|emit', { event: name, payload: payload });
      };
    }
  }
  if (!emit) return;

  // The tab strip is part of the page, not a separate title bar: keep it
  // transparent. Injected because this shell may load a payload whose CSS still
  // painted it with the page-background token.
  try {
    var stripStyle = document.createElement('style');
    stripStyle.textContent = '.desktop-tab-bar{background-color:transparent!important}';
    (document.head || document.documentElement).appendChild(stripStyle);
  } catch (e) {}

  // Desktop default: turn OS notifications ON for a first run, without ever
  // overriding a user who has explicitly turned them off. The storage key is the
  // one `src/lib/alerts/browser-notifier.ts` reads. The browser keeps its opt-in
  // behaviour because this script only runs inside the shell.
  try {
    if (window.localStorage.getItem('be_alerts_browser_v1') === null) {
      window.localStorage.setItem('be_alerts_browser_v1', '1');
    }
  } catch (e) {}

  // Desktop default: open with the FULL sidebar. The icon rail is a choice the
  // user can still make at runtime (Ctrl/Cmd+B); it must not be restored from an
  // earlier session and leave the desktop shell looking collapsed.
  try {
    window.localStorage.setItem('be_sidebar_collapsed_v1', '0');
  } catch (e) {}

  function NativeNotification(title, opts) {    opts = opts || {};
    this.title = title;
    this.body = opts.body || '';
    this.tag = opts.tag || '';
    this.icon = opts.icon || '';
    this.onclick = null;
    this.onclose = null;
    this.onerror = null;
    try {
      emit('be-notify', {
        title: String(title == null ? 'Black Eclipse' : title),
        body: String(opts.body == null ? '' : opts.body)
      });
    } catch (e) {}
  }
  NativeNotification.permission = 'granted';
  NativeNotification.maxActions = 2;
  NativeNotification.requestPermission = function () {
    return Promise.resolve('granted');
  };
  NativeNotification.prototype.close = function () {};
  try {
    Object.defineProperty(window, 'Notification', {
      value: NativeNotification,
      writable: true,
      configurable: true
    });
  } catch (e) {}

  // Shell-level shortcuts. Deliberately no Ctrl+R: reloading the app would
  // discard unsaved composer state, and the app's own shortcuts already cover
  // navigation.
  window.addEventListener('keydown', function (e) {
    try {
      if (e.key === 'F11') {
        e.preventDefault();
        emit('be-shortcut', { action: 'fullscreen' });
      } else if (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'i')) {
        e.preventDefault();
        emit('be-shortcut', { action: 'devtools' });
      }
    } catch (err) {}
  }, true);

  // Frameless window chrome. The app's tab strip marks empty space with
  // `data-be-drag`; interactive children opt out with `data-be-no-drag`. Window
  // buttons (and the splash) use the same `be-window` event -> Rust bridge.
  function windowAction(action) {
    try { emit('be-window', { action: action }); } catch (e) {}
  }
  window.addEventListener('be-window-action', function (e) {
    var detail = (e && e.detail) || {};
    if (detail.action) emit('be-window', detail);
  });
  document.addEventListener('mousedown', function (e) {
    if (e.button !== 0) return;
    var target = e.target;
    if (!target || !target.closest) return;
    if (target.closest('[data-be-no-drag]')) return;
    if (!target.closest('[data-be-drag]')) return;
    windowAction('start-drag');
  }, true);
  document.addEventListener('dblclick', function (e) {
    var target = e.target;
    if (!target || !target.closest) return;
    if (target.closest('[data-be-no-drag]') || !target.closest('[data-be-drag]')) return;
    windowAction('toggle-maximize');
  }, true);
})();
"#;

#[derive(Serialize, Deserialize, Clone, Debug)]
struct Prefs {
    keep_warm: bool,
    width: u32,
    height: u32,
    x: Option<i32>,
    y: Option<i32>,
    maximized: bool,
    /// Translucent, acrylic-blurred window (desktop only). The app's sidebar
    /// stays opaque; see `apply_window_glass`.
    #[serde(default = "default_window_glass")]
    window_glass: bool,
}

fn default_window_glass() -> bool {
    true
}

impl Default for Prefs {
    fn default() -> Self {
        Self {
            keep_warm: true,
            width: 1440,
            height: 900,
            x: None,
            y: None,
            maximized: false,
            window_glass: true,
        }
    }
}

struct AppState {
    root: PathBuf,
    prefs_file: PathBuf,
    prefs: Mutex<Prefs>,
    child: Mutex<Option<Child>>,
    /// Throttles bounds writes: Windows emits drag/resize events continuously.
    last_bounds_save: Mutex<Instant>,
    /// One supervisor at a time; the retry button must not stack boot attempts.
    supervising: AtomicBool,
    /// True only when this shell started the server. An attached server belongs
    /// to the browser path and must never be killed on quit.
    owns_server: AtomicBool,
    quitting: AtomicBool,
    /// Presentation state for the borderless window. Windows' native `maximize`
    /// fills the whole monitor (taskbar included) for a frameless window, so the
    /// shell emulates maximize by filling the monitor's WORK AREA instead.
    maximized: AtomicBool,
}

fn log_line(line: &str) {
    // Bounded, append-only. Never let a chatty server fill the disk.
    let path = std::env::var("BE_DESKTOP_LOG").ok().map(PathBuf::from);
    if let Some(path) = path {
        if let Ok(meta) = fs::metadata(&path) {
            if meta.len() > 8 * 1024 * 1024 {
                let _ = fs::write(&path, b"");
            }
        }
        if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(&path) {
            let _ = writeln!(f, "{line}");
        }
    }
}

/// Locate the repository root by walking up from the executable and looking for
/// the bootstrap script. Works for `target/debug`, `target/release` and a
/// future packaged layout without any hard-coded depth.
fn resolve_root() -> Option<PathBuf> {
    // Packaged layout: <exe dir>\app\scripts\desktop-server.js
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let packaged = dir.join("app");
            if packaged.join("scripts/desktop-server.js").exists() {
                return Some(packaged);
            }
        }
    }
    if let Ok(explicit) = std::env::var("BE_DESKTOP_ROOT") {
        let p = PathBuf::from(explicit);
        if p.join("scripts/desktop-server.js").exists() {
            return Some(p);
        }
    }
    let mut dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    for _ in 0..10 {
        if dir.join("scripts/desktop-server.js").exists() {
            return Some(dir);
        }
        dir = dir.parent()?.to_path_buf();
    }
    None
}

/// Node is required. A packaged install ships `<exe dir>\runtime\node.exe`, so it
/// never depends on the user having Node; a repository checkout uses PATH first.
fn find_node() -> Option<String> {
    // A packaged install ships its own Node, named per platform.
    let node_name = if cfg!(windows) { "node.exe" } else { "node" };
    let bundled = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|d| d.join("runtime").join(node_name)));
    if let Some(path) = bundled {
        if path.exists() {
            return Some(path.to_string_lossy().to_string());
        }
    }

    if Command::new("node")
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
    {
        return Some("node".to_string());
    }

    let mut candidates: Vec<PathBuf> = Vec::new();

    #[cfg(windows)]
    {
        if let Ok(pf) = std::env::var("ProgramFiles") {
            candidates.push(PathBuf::from(pf).join("nodejs").join("node.exe"));
        }
        if let Ok(pf) = std::env::var("ProgramFiles(x86)") {
            candidates.push(PathBuf::from(pf).join("nodejs").join("node.exe"));
        }
        if let Ok(la) = std::env::var("LOCALAPPDATA") {
            candidates.push(
                PathBuf::from(la)
                    .join("Programs")
                    .join("nodejs")
                    .join("node.exe"),
            );
        }
    }

    #[cfg(not(windows))]
    {
        // Common install locations for a developer checkout. A packaged install
        // always finds its bundled runtime above and never reaches here.
        for p in ["/usr/local/bin/node", "/opt/homebrew/bin/node", "/usr/bin/node"] {
            candidates.push(PathBuf::from(p));
        }
    }

    candidates
        .into_iter()
        .find(|p| p.exists())
        .map(|p| p.to_string_lossy().to_string())
}

fn emit_status(app: &AppHandle, kind: &str, message: &str) {
    let _ = app.emit(
        "be-status",
        serde_json::json!({ "kind": kind, "message": message }),
    );
}

fn load_prefs(path: &PathBuf) -> Prefs {
    fs::read_to_string(path)
        .ok()
        .and_then(|s| serde_json::from_str::<Prefs>(&s).ok())
        .unwrap_or_default()
}

fn save_prefs(path: &PathBuf, prefs: &Prefs) {
    if let Ok(json) = serde_json::to_string_pretty(prefs) {
        let _ = fs::write(path, json);
    }
}

/// Kill the whole process tree. `next start` runs as a grandchild (Rust →
/// bootstrap → next), and `Child::kill` does not reap descendants on Windows.
fn kill_tree(state: &AppState) {
    if !state.owns_server.load(Ordering::SeqCst) {
        return;
    }
    let mut guard = match state.child.lock() {
        Ok(g) => g,
        Err(_) => return,
    };
    if let Some(mut child) = guard.take() {
        let pid = child.id();
        #[cfg(windows)]
        {
            let _ = Command::new("taskkill")
                .args(["/PID", &pid.to_string(), "/T", "/F"])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }
        // On Unix the child was started in its own session (see `spawn_bootstrap`),
        // so signalling the process group takes the Next server and the Python
        // harness with it — `Child::kill` alone would orphan both.
        #[cfg(unix)]
        {
            unsafe {
                libc::kill(-(pid as i32), libc::SIGKILL);
            }
        }
        let _ = child.kill();
        let _ = child.wait();
        log_line(&format!("[shell] server tree {pid} stopped"));
    }
}

fn navigate_to_app(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let url: tauri::Url = match format!("http://127.0.0.1:{}/", app_port()).parse() {
            Ok(u) => u,
            Err(_) => return,
        };
        let _ = win.navigate(url);
        maybe_run_diagnostics(app);
    }
}

/// Replace the current page with an in-place failure panel. Used when an owned
/// server dies after the app is already showing: a dead UI that silently
/// swallows every click is the worst possible outcome.
fn show_failure_overlay(app: &AppHandle, message: &str) {
    let win = match app.get_webview_window("main") {
        Some(w) => w,
        None => return,
    };
    let quoted = serde_json::to_string(message).unwrap_or_else(|_| "\"Server stopped\"".to_string());
    let script = format!(
        r#"(function () {{
  if (document.getElementById('be-failure')) return;
  var wrap = document.createElement('div');
  wrap.id = 'be-failure';
  wrap.style.cssText = 'position:fixed;inset:0;z-index:2147483647;display:flex;align-items:center;justify-content:center;background:rgba(8,8,10,0.94);font-family:"Segoe UI",system-ui,sans-serif;color:#fafafa';
  var card = document.createElement('div');
  card.style.cssText = 'max-width:440px;padding:28px 30px;border:1px solid rgba(255,255,255,0.1);border-radius:16px;background:rgba(24,24,27,0.92);text-align:center';
  var title = document.createElement('div');
  title.textContent = 'Black Eclipse';
  title.style.cssText = 'font-size:15px;font-weight:600;margin-bottom:8px';
  var body = document.createElement('div');
  body.textContent = {quoted};
  body.style.cssText = 'font-size:12.5px;color:rgba(250,250,250,0.62);line-height:1.55;margin-bottom:16px';
  var btn = document.createElement('button');
  btn.textContent = 'Reload';
  btn.style.cssText = 'font:inherit;font-size:12px;padding:7px 14px;border-radius:8px;border:1px solid rgba(255,255,255,0.12);background:rgba(255,255,255,0.08);color:#fafafa;cursor:pointer';
  btn.addEventListener('click', function () {{ location.reload(); }});
  card.appendChild(title);
  card.appendChild(body);
  card.appendChild(btn);
  wrap.appendChild(card);
  document.body.appendChild(wrap);
}})();"#
    );
    let _ = win.eval(script);
}

/// WebView2 is part of Windows 11 but not guaranteed on Windows 10. Detect it
/// before building the window so a missing runtime produces instructions rather
/// than a shell that opens nothing.
#[cfg(windows)]
fn webview2_version() -> Option<String> {
    const KEYS: [&str; 3] = [
        r"HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        r"HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        r"HKCU\Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    ];
    for key in KEYS {
        let out = Command::new("reg").args(["query", key, "/v", "pv"]).output();
        if let Ok(out) = out {
            if out.status.success() {
                let text = String::from_utf8_lossy(&out.stdout);
                if let Some(line) = text.lines().find(|l| l.contains("REG_SZ")) {
                    if let Some(pv) = line.split("REG_SZ").nth(1) {
                        let v = pv.trim().to_string();
                        if !v.is_empty() {
                            return Some(v);
                        }
                    }
                }
            }
        }
    }
    None
}

#[cfg(windows)]
fn message_box(text: &str) {
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;

    #[link(name = "user32")]
    extern "system" {
        fn MessageBoxW(hwnd: *mut std::ffi::c_void, text: *const u16, caption: *const u16, utype: u32) -> i32;
    }

    let wide = |s: &str| -> Vec<u16> { OsStr::new(s).encode_wide().chain(Some(0)).collect() };
    let title = wide("Black Eclipse");
    let body = wide(text);
    // 0x10 = MB_ICONERROR, 0x0 = MB_OK, foreground
    unsafe {
        MessageBoxW(std::ptr::null_mut(), body.as_ptr(), title.as_ptr(), 0x10);
    }
}

/// Thread: run one supervision attempt, then allow the splash's retry button to
/// start another. A stuck `supervising` flag would make "Try again" dead.
fn start_supervisor(app: AppHandle) {
    std::thread::spawn(move || {
        if app.state::<AppState>().supervising.swap(true, Ordering::SeqCst) {
            return;
        }
        supervise(app.clone());
        app.state::<AppState>()
            .supervising
            .store(false, Ordering::SeqCst);
    });
}

/// Spawn the bootstrap, stream its output to the log, and translate the
/// `@@BE:*@@` markers into splash events.
fn supervise(app: AppHandle) {
    let state = app.state::<AppState>();
    let root = state.root.clone();

        let node = match find_node() {
            Some(n) => n,
            None => {
                emit_status(
                    &app,
                    "error",
                    "Node.js was not found. Install it from nodejs.org, then reopen Black Eclipse.",
                );
                return;
            }
        };

        emit_status(&app, "info", "Starting Black Eclipse…");

        let mut cmd = Command::new(&node);
        cmd.arg("scripts/desktop-server.js")
            .current_dir(&root)
            .env("BE_DESKTOP_SHELL", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            // CREATE_NO_WINDOW: no console flash for the child.
            cmd.creation_flags(0x0800_0000);
        }
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            // Own session, so `kill_tree` can signal the whole group and take the
            // Next server and the Python harness down with the bootstrap.
            unsafe {
                cmd.pre_exec(|| {
                    if libc::setsid() == -1 {
                        return Err(std::io::Error::last_os_error());
                    }
                    Ok(())
                });
            }
        }

        let mut child = match cmd.spawn() {
            Ok(c) => c,
            Err(e) => {
                emit_status(&app, "error", &format!("Could not start the server: {e}"));
                return;
            }
        };

        let stdout = child.stdout.take();
        let stderr = child.stderr.take();

        // Store the handle IMMEDIATELY. The server keeps writing to stdout for
        // its whole life, so the read loop below never returns while it is
        // healthy — deferring the store would leave the process unkillable.
        if let Ok(mut guard) = state.child.lock() {
            *guard = Some(child);
        }

        if let Some(err) = stderr {
            std::thread::spawn(move || {
                // Byte-wise, lossy: Next and the Python harness can emit bytes
                // that are not valid UTF-8 on a Windows console. `lines()` would
                // return an error and end the stream, silently killing the log.
                let mut reader = BufReader::new(err);
                let mut buf = Vec::new();
                loop {
                    buf.clear();
                    match reader.read_until(b'\n', &mut buf) {
                        Ok(0) | Err(_) => break,
                        Ok(_) => {
                            let line = String::from_utf8_lossy(&buf);
                            log_line(&format!("[server:err] {}", line.trim_end()));
                        }
                    }
                }
            });
        }

        let mut ready = false;

        if let Some(out) = stdout {
            let mut reader = BufReader::new(out);
            let mut buf = Vec::new();
            loop {
                buf.clear();
                match reader.read_until(b'\n', &mut buf) {
                    Ok(0) | Err(_) => break,
                    Ok(_) => {}
                }
                let line = String::from_utf8_lossy(&buf).trim_end().to_string();
                if let Some(rest) = line.strip_prefix("@@BE:") {
                    if let Some((kind, payload)) = rest.split_once("@@") {
                        match kind {
                            "ATTACH" => {
                                state.owns_server.store(false, Ordering::SeqCst);
                                // The bootstrapper exits right after this marker:
                                // release the handle so we never taskkill a
                                // server that belongs to the browser path.
                                if let Ok(mut guard) = state.child.lock() {
                                    guard.take();
                                }
                                log_line(&format!(
                                    "[shell] attaching to an already-running server ({payload})"
                                ));
                                emit_status(&app, "info", "Connecting to the running server...");
                                navigate_to_app(&app);
                                ready = true;
                            }
                            "CONFLICT" => {
                                state.owns_server.store(false, Ordering::SeqCst);
                                if let Ok(mut guard) = state.child.lock() {
                                    guard.take();
                                }
                                log_line(&format!("[shell] conflict: {payload}"));
                                emit_status(&app, "error", payload);
                            }
                            "WARN" => {
                                log_line(&format!("[shell] warn: {payload}"));
                                emit_status(&app, "info", payload);
                            }
                            "ERROR" => {
                                log_line(&format!("[shell] error: {payload}"));
                                emit_status(&app, "error", payload);
                            }
                            "READY" => {
                                state.owns_server.store(true, Ordering::SeqCst);
                                emit_status(&app, "ready", "Opening...");
                                navigate_to_app(&app);
                                ready = true;
                            }
                            _ => {}
                        }
                        continue;
                    }
                }
                log_line(&format!("[server] {line}"));
            }
        }

        // Reap the bootstrap if it exited on its own; a live server keeps its
        // handle in state for shutdown.
        let exited = match state.child.lock() {
            Ok(mut guard) => guard.take(),
            Err(_) => None,
        };
        if let Some(mut child) = exited {
            let _ = child.wait();
        }

        if ready && state.owns_server.load(Ordering::SeqCst) {
            // The server died AFTER the app was showing. Swap the page for an
            // in-place failure panel rather than leaving a dead UI that silently
            // swallows every click.
            log_line("[shell] owned server exited after readiness");
            show_failure_overlay(
                &app,
                "The Black Eclipse server stopped unexpectedly. Your data is safe. Use Retry to start it again.",
            );
            emit_status(&app, "error", "The server stopped unexpectedly.");
        } else if !ready {
            emit_status(
                &app,
                "error",
                "The server stopped before the app became ready. See .black-eclipse/desktop-native.log.",
            );
        }
}

/// After the window has navigated to the app, prove the whole notification
/// chain: init script installed → `Notification` shim → native command → OS
/// toast. Gated by `BE_DESKTOP_DIAGNOSTICS=1` so it can never fire in normal use.
///
/// The probe reports through the webview URL (`history.replaceState`, no reload)
/// rather than through IPC, because proving IPC is one of the things under test.
/// If IPC were the channel, a broken IPC would look identical to a broken probe.
fn maybe_run_diagnostics(app: &AppHandle) {
    if std::env::var("BE_DESKTOP_DIAGNOSTICS").ok().as_deref() != Some("1") {
        return;
    }
    let handle = app.clone();
    std::thread::spawn(move || {
        // The app is a heavy client; give hydration a moment.
        std::thread::sleep(Duration::from_secs(6));
        let win = match handle.get_webview_window("main") {
            Some(w) => w,
            None => return,
        };
        log_line("[diag] injecting notification probe into the app origin");

        // Safe tokens only: the result travels in the URL, so no decoding.
        let probe = r#"(function () {
  var safe = function (v) {
    return String(v == null ? 'none' : v).replace(/[^A-Za-z0-9_.-]/g, '');
  };
  var out = [];
  var T = window.__TAURI__;
  var invoke = T && T.core && T.core.invoke;
  out.push('hn:' + (typeof Notification !== 'undefined' ? 1 : 0));
  out.push('perm:' + safe(typeof Notification !== 'undefined' ? Notification.permission : 'undefined'));
  out.push('sec:' + (window.isSecureContext === true ? 1 : 0));
  out.push('tauri:' + (invoke ? 1 : 0));
  out.push('ctor:' + safe(typeof Notification !== 'undefined' && Notification.name ? Notification.name : 'none'));
  try {
    out.push('pref:' + safe(window.localStorage.getItem('be_alerts_browser_v1')));
  } catch (e) {
    out.push('pref:locked');
  }

  var shimCall = 'skipped';
  try {
    new Notification('Black Eclipse', { body: 'Diag: shim path.' });
    shimCall = 'dispatched';
  } catch (e) {
    shimCall = 'err-' + safe(e && e.message ? e.message : e);
  }
  out.push('shimcall:' + shimCall);

  var direct = (T && T.event && typeof T.event.emit === 'function')
    ? T.event.emit('be-notify', { title: 'Black Eclipse', body: 'Diag: direct event path.' })
        .then(function () { return 'ok'; })
        .catch(function (e) { return 'err-' + safe(e && e.message ? e.message : e); })
    : Promise.resolve('noevent');

  direct.then(function (result) {
    out.push('direct:' + result);
    try {
      history.replaceState(null, '', '/?diag=' + out.join('~'));
    } catch (e) {}
  });
})();"#;
        let _ = win.eval(probe);

        // Poll the webview URL for the report.
        for _ in 0..40 {
            std::thread::sleep(Duration::from_millis(500));
            if let Ok(url) = win.url() {
                let text = url.as_str();
                if let Some(idx) = text.find("diag=") {
                    let rest = &text[idx + 5..];
                    let payload = rest.split('&').next().unwrap_or(rest);
                    log_line(&format!("[diag] {payload}"));
                    return;
                }
            }
        }
        log_line("[diag] no report received (probe blocked or page replaced)");
    });
}

#[tauri::command]
fn desktop_diag_report(payload: String) {
    log_line(&format!("[diag] {payload}"));
}

/// Window chrome actions. The app is served from a remote (loopback) origin,
/// where app-defined commands are denied, so the webview reaches this through
/// the `be-window` event; the bundled splash can invoke the command directly.
/// The active monitor's work area as `(x, y, width, height)` in physical pixels.
fn work_area_of(app: &AppHandle) -> Option<(i32, i32, u32, u32)> {
    let win = app.get_webview_window("main")?;
    let monitor = win
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| app.primary_monitor().ok().flatten())?;
    let work = monitor.work_area();
    Some((work.position.x, work.position.y, work.size.width, work.size.height))
}

/// Emulated maximize for a frameless window: fill the monitor's WORK AREA so the
/// Windows taskbar stays visible. Native `maximize()` on `decorations(false)`
/// covers the taskbar, which hid the bottom of the app.
fn fill_work_area(app: &AppHandle) {
    let Some(win) = app.get_webview_window("main") else {
        return;
    };
    let Some((x, y, width, height)) = work_area_of(app) else {
        return;
    };
    // A frameless window still has invisible resize borders: size the INNER
    // area so the visible content (not the invisible frame) ends at the work
    // area's bottom edge.
    let (border_w, border_h) = match (win.outer_size(), win.inner_size()) {
        (Ok(outer), Ok(inner)) => (
            outer.width.saturating_sub(inner.width),
            outer.height.saturating_sub(inner.height),
        ),
        _ => (0, 0),
    };
    let _ = win.set_position(tauri::PhysicalPosition::new(x, y));
    let _ = win.set_size(tauri::PhysicalSize::new(
        width.saturating_sub(border_w),
        height.saturating_sub(border_h),
    ));
    log_line(&format!(
        "[window] fill work area {width}x{height} at {x},{y} (border {border_w}x{border_h}) -> inner={:?} outer={:?}",
        win.inner_size().ok(),
        win.outer_size().ok()
    ));
}

/// Restore the last windowed bounds saved before the emulated maximize.
fn restore_windowed(app: &AppHandle) {
    let Some(win) = app.get_webview_window("main") else {
        return;
    };
    let state = app.state::<AppState>();
    let (width, height, x, y) = match state.prefs.lock() {
        Ok(prefs) => (prefs.width, prefs.height, prefs.x, prefs.y),
        Err(_) => return,
    };
    let _ = win.set_size(tauri::PhysicalSize::new(width, height));
    if let (Some(x), Some(y)) = (x, y) {
        let _ = win.set_position(tauri::PhysicalPosition::new(x, y));
    }
}

fn toggle_maximize(app: &AppHandle) {
    let state = app.state::<AppState>();
    if state.maximized.load(Ordering::SeqCst) {
        state.maximized.store(false, Ordering::SeqCst);
        if let Ok(mut prefs) = state.prefs.lock() {
            prefs.maximized = false;
            save_prefs(&state.prefs_file, &prefs);
        }
        restore_windowed(app);
    } else {
        // Remember the windowed geometry BEFORE filling the work area; the
        // Resized event that follows must not overwrite it (persist_bounds
        // skips while `maximized` is set).
        if let Some(win) = app.get_webview_window("main") {
            if let (Ok(size), Ok(pos)) = (win.inner_size(), win.outer_position()) {
                if let Ok(mut prefs) = state.prefs.lock() {
                    prefs.width = size.width;
                    prefs.height = size.height;
                    prefs.x = Some(pos.x);
                    prefs.y = Some(pos.y);
                    prefs.maximized = true;
                    save_prefs(&state.prefs_file, &prefs);
                }
            }
        }
        state.maximized.store(true, Ordering::SeqCst);
        fill_work_area(app);
    }
}

/// Apply or clear the OS-level glass behind the WebView. Acrylic is the real
/// blur (the CSS cannot blur the desktop); `apply_blur` is the older fallback.
#[cfg(windows)]
fn apply_window_glass(win: &WebviewWindow, enabled: bool) {
    use window_vibrancy::{apply_acrylic, apply_blur, clear_acrylic, clear_blur};
    if enabled {
        match apply_acrylic(win, Some((8, 9, 12, 175))) {
            Ok(()) => log_line("[window] acrylic enabled"),
            Err(err) => {
                log_line(&format!("[window] acrylic failed: {err}; trying blur"));
                match apply_blur(win, Some((10, 10, 12, 200))) {
                    Ok(()) => log_line("[window] blur fallback enabled"),
                    Err(err) => log_line(&format!("[window] blur failed: {err}")),
                }
            }
        }
    } else {
        let _ = clear_acrylic(win);
        let _ = clear_blur(win);
        log_line("[window] glass disabled");
    }
}

#[cfg(not(windows))]
fn apply_window_glass(_win: &WebviewWindow, _enabled: bool) {}

fn set_window_glass(app: &AppHandle, enabled: bool) {
    if let Some(win) = app.get_webview_window("main") {
        apply_window_glass(&win, enabled);
    }
    let state = app.state::<AppState>();
    if let Ok(mut prefs) = state.prefs.lock() {
        if prefs.window_glass != enabled {
            prefs.window_glass = enabled;
            save_prefs(&state.prefs_file, &prefs);
        }
    };
}

fn perform_window_action(app: &AppHandle, action: &str) {
    let win = match app.get_webview_window("main") {
        Some(win) => win,
        None => return,
    };
    log_line(&format!("[window] {action}"));
    match action {
        "minimize" => {
            let _ = win.minimize();
        }
        "toggle-maximize" => toggle_maximize(app),
        "close" => {
            let _ = win.close();
        }
        "start-drag" => {
            let _ = win.start_dragging();
        }
        _ => {}
    }
}

#[tauri::command]
fn desktop_window_action(app: AppHandle, action: String) {
    perform_window_action(&app, &action);
}

fn notify_native(app: &AppHandle, title: &str, body: &str) {
    use tauri_plugin_notification::NotificationExt;
    match app.notification().builder().title(title).body(body).show() {
        Ok(()) => log_line(&format!("[notify] sent: {title}")),
        Err(err) => log_line(&format!("[notify] failed: {err}")),
    }
}

#[tauri::command]
fn desktop_notify(app: AppHandle, title: String, body: String) {
    notify_native(&app, &title, &body);
}

#[tauri::command]
fn desktop_toggle_fullscreen(app: AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let full = win.is_fullscreen().unwrap_or(false);
        let _ = win.set_fullscreen(!full);
    }
}

#[tauri::command]
fn desktop_devtools(app: AppHandle) {
    #[cfg(debug_assertions)]
    if let Some(win) = app.get_webview_window("main") {
        win.open_devtools();
    }
    #[cfg(not(debug_assertions))]
    let _ = &app;
}

#[tauri::command]
fn desktop_retry(app: AppHandle) {
    start_supervisor(app);
}

#[tauri::command]
fn desktop_info(state: tauri::State<AppState>) -> serde_json::Value {
    serde_json::json!({
        "root": state.root.to_string_lossy(),
        "port": app_port(),
        "keepWarm": state.prefs.lock().map(|p| p.keep_warm).unwrap_or(true),
    })
}

fn show_window(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.unminimize();
        let _ = win.set_focus();
    }
}

/// Saved bounds can exceed the monitor's WORK AREA (a previous resize, a
/// different taskbar size, a resolution change). Restoring them verbatim puts
/// the bottom of the frameless window under the Windows taskbar. Clamp both the
/// size and the position to the work area of the monitor the window belongs to.
fn clamped_bounds(app: &AppHandle, prefs: &Prefs) -> (f64, f64, Option<(f64, f64)>) {
    // Pick the monitor that physically contains the saved point. `monitor_from_point`
    // takes LOGICAL coordinates, while prefs are physical, so scan the monitor
    // rects directly and fall back to the primary monitor.
    let monitor = app
        .available_monitors()
        .ok()
        .and_then(|monitors| {
            monitors.into_iter().find(|monitor| {
                let origin = monitor.position();
                let size = monitor.size();
                match (prefs.x, prefs.y) {
                    (Some(x), Some(y)) => {
                        x >= origin.x
                            && x < origin.x + size.width as i32
                            && y >= origin.y
                            && y < origin.y + size.height as i32
                    }
                    _ => false,
                }
            })
        })
        .or_else(|| app.primary_monitor().ok().flatten());

    let Some(monitor) = monitor else {
        return (
            prefs.width as f64,
            prefs.height as f64,
            prefs.x.zip(prefs.y).map(|(x, y)| (x as f64, y as f64)),
        );
    };

    let work = monitor.work_area();
    // Builder sizes/positions are LOGICAL; prefs and the work area are physical.
    let scale = monitor.scale_factor().max(0.5);
    let min_w = 880.0 * scale;
    let min_h = 620.0 * scale;
    let max_w = (work.size.width as f64).max(min_w);
    let max_h = (work.size.height as f64).max(min_h);
    let width_px = (prefs.width as f64).clamp(min_w, max_w);
    let height_px = (prefs.height as f64).clamp(min_h, max_h);

    let position = prefs.x.zip(prefs.y).map(|(x, y)| {
        let max_x = (work.position.x + work.size.width as i32 - width_px as i32).max(work.position.x);
        let max_y = (work.position.y + work.size.height as i32 - height_px as i32).max(work.position.y);
        (
            x.clamp(work.position.x, max_x) as f64 / scale,
            y.clamp(work.position.y, max_y) as f64 / scale,
        )
    });

    (width_px / scale, height_px / scale, position)
}

fn build_window(app: &AppHandle, prefs: &Prefs) -> tauri::Result<WebviewWindow> {
    let (width, height, position) = clamped_bounds(app, prefs);
    let mut builder = WebviewWindowBuilder::new(app, "main", WebviewUrl::App(SPLASH.into()))
        .title("Black Eclipse")
        .inner_size(width, height)
        .min_inner_size(880.0, 620.0)
        // Frameless: the app's own tab strip is the title bar (drag region +
        // minimize/maximize/close). The native title text/logo is gone; the
        // title stays for the taskbar and accessibility.
        .decorations(false)
        .initialization_script(INIT_SCRIPT);

    // A transparent window is what lets the acrylic/blur layer show through the
    // WebView. The app paints an opaque background when the glass setting is
    // off, so transparency itself is always safe.
    #[cfg(windows)]
    {
        builder = builder
            .transparent(true)
            .background_color(tauri::window::Color(0, 0, 0, 0));
    }
    #[cfg(not(windows))]
    {
        builder = builder.background_color(tauri::window::Color(10, 10, 12, 255));
    }

    if let Some((x, y)) = position {
        builder = builder.position(x, y);
    } else {
        builder = builder.center();
    }

    let win = builder.build()?;

    apply_window_glass(&win, prefs.window_glass);

    log_line(&format!(
        "[window] restore inner={}x{} logical at {:?}; actual={:?}",
        width.round(),
        height.round(),
        position,
        win.inner_size().ok()
    ));

    if prefs.maximized {
        // Re-assert after the first paint: Windows can apply the builder size
        // asynchronously, which would otherwise undo the work-area fill.
        let app_for_fill = app.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(300));
            fill_work_area(&app_for_fill);
        });
    }

    Ok(win)
}

fn persist_bounds(app: &AppHandle) {
    let state = app.state::<AppState>();
    // Emulated maximize must not overwrite the saved WINDOWED geometry.
    if state.maximized.load(Ordering::SeqCst) {
        return;
    }
    let prefs_file = state.prefs_file.clone();
    let win = match app.get_webview_window("main") {
        Some(w) => w,
        None => return,
    };

    if win.is_maximized().unwrap_or(false) {
        // Never record the maximized geometry as the restore geometry.
        if let Ok(mut prefs) = state.prefs.lock() {
            prefs.maximized = true;
            save_prefs(&prefs_file, &prefs);
        }
        return;
    }

    // Windows emits drag/resize events continuously; write at most ~2/second.
    let allowed = match state.last_bounds_save.lock() {
        Ok(mut last) => {
            if last.elapsed() < Duration::from_millis(400) {
                false
            } else {
                *last = Instant::now();
                true
            }
        }
        Err(_) => true,
    };
    if !allowed {
        return;
    }

    let size = win.inner_size().ok();
    let pos = win.outer_position().ok();
    write_bounds(&state, size, pos);
}

/// Split out of `persist_bounds` so the `MutexGuard` temporary is dropped at
/// the call boundary instead of at the end of the caller's scope.
fn write_bounds(state: &AppState, size: Option<tauri::PhysicalSize<u32>>, pos: Option<tauri::PhysicalPosition<i32>>) {
    if let Ok(mut prefs) = state.prefs.lock() {
        if let Some(size) = size {
            if size.width > 200 && size.height > 200 {
                prefs.width = size.width;
                prefs.height = size.height;
            }
        }
        if let Some(pos) = pos {
            prefs.x = Some(pos.x);
            prefs.y = Some(pos.y);
        }
        prefs.maximized = false;
        save_prefs(&state.prefs_file, &prefs);
    }
}

fn main() {
    let root = match resolve_root() {
        Some(r) => r,
        None => {
            // Nothing to attach to the UI yet; fail loudly in the log.
            eprintln!("[black-eclipse] could not locate the application root (scripts/desktop-server.js)");
            return;
        }
    };

    let runtime_dir = root.join(".black-eclipse");
    let _ = fs::create_dir_all(&runtime_dir);
    let prefs_file = runtime_dir.join("desktop-prefs.json");
    let log_file = runtime_dir.join("desktop-native.log");
    std::env::set_var("BE_DESKTOP_LOG", &log_file);

    let prefs = load_prefs(&prefs_file);

    log_line(&format!(
        "[shell] starting — root={} port={}",
        root.to_string_lossy(),
        app_port()
    ));

    // Tauri's capability URL patterns cannot wildcard the port, so IPC (and with
    // it desktop notifications) is only granted on the canonical port. Say so
    // instead of letting a non-default port fail silently.
    if app_port() != APP_PORT {
        log_line(&format!(
            "[shell] WARNING: port {} is not the canonical {APP_PORT}; desktop notifications \
             will not work because the app origin is not in the IPC allowlist",
            app_port()
        ));
    }

    // §7: never open a window that cannot render. WebView2 ships with Windows 11
    // but not every Windows 10 machine.
    #[cfg(windows)]
    match webview2_version() {
        Some(version) => log_line(&format!("[shell] WebView2 runtime {version}")),
        None => {
            log_line("[shell] WebView2 runtime not found");
            message_box(
                "Black Eclipse needs the Microsoft Edge WebView2 Runtime, which is not installed.\n\n\
                 Install it from:\nhttps://developer.microsoft.com/microsoft-edge/webview2/\n\n\
                 Meanwhile the browser version still works: run `npm start` in the project \
                 folder, then open http://127.0.0.1:3100.",
            );
            return;
        }
    }

    // macOS (WKWebView) and Linux (WebKitGTK) use an OS-provided webview, so
    // there is nothing to detect there.
    #[cfg(not(windows))]
    log_line("[shell] using the system webview (no runtime probe needed)");

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_window(app);
        }))
        .plugin(tauri_plugin_notification::init())
        .manage(AppState {
            root: root.clone(),
            prefs_file: prefs_file.clone(),
            prefs: Mutex::new(prefs.clone()),
            child: Mutex::new(None),
            last_bounds_save: Mutex::new(Instant::now() - Duration::from_secs(2)),
            supervising: AtomicBool::new(false),
            owns_server: AtomicBool::new(false),
            quitting: AtomicBool::new(false),
            maximized: AtomicBool::new(prefs.maximized),
        })
        .invoke_handler(tauri::generate_handler![
            desktop_notify,
            desktop_retry,
            desktop_window_action,
            desktop_toggle_fullscreen,
            desktop_devtools,
            desktop_diag_report,
            desktop_info
        ])
        .setup(move |app| {
            let handle = app.handle().clone();
            let win = build_window(&handle, &prefs)?;

            // --- window lifecycle -------------------------------------------------
            let win_for_events = win.clone();
            let app_for_events = handle.clone();
            win.on_window_event(move |event| match event {
                WindowEvent::CloseRequested { api, .. } => {
                    let state = app_for_events.state::<AppState>();
                    let keep_warm = state
                        .prefs
                        .lock()
                        .map(|p| p.keep_warm)
                        .unwrap_or(false);
                    let quitting = state.quitting.load(Ordering::SeqCst);
                    if keep_warm && !quitting {
                        // Keep the server warm so reopening is instant.
                        api.prevent_close();
                        log_line("[shell] window hidden (keep-warm)");
                        let _ = win_for_events.hide();
                    } else {
                        let _ = win_for_events.hide();
                        let state = app_for_events.state::<AppState>();
                        state.quitting.store(true, Ordering::SeqCst);
                        kill_tree(&state);
                        app_for_events.exit(0);
                    }
                }
                WindowEvent::Moved(_) | WindowEvent::Resized(_) => {
                    persist_bounds(&app_for_events);
                }
                _ => {}
            });

            // --- tray -------------------------------------------------------------
            let open_item = MenuItem::with_id(&handle, "open", "Open Black Eclipse", true, None::<&str>)?;
            let keep_item = CheckMenuItem::with_id(
                &handle,
                "keep_warm",
                "Keep running when the window closes",
                true,
                prefs.keep_warm,
                None::<&str>,
            )?;
            let quit_item = MenuItem::with_id(&handle, "quit", "Quit Black Eclipse", true, None::<&str>)?;
            let separator = PredefinedMenuItem::separator(&handle)?;
            let menu = Menu::with_items(&handle, &[&open_item, &keep_item, &separator, &quit_item])?;

            let mut tray = TrayIconBuilder::with_id("main-tray")
                .tooltip("Black Eclipse")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_window(app),
                    "keep_warm" => {
                        let state = app.state::<AppState>();
                        let mut next = true;
                        if let Ok(mut prefs) = state.prefs.lock() {
                            prefs.keep_warm = !prefs.keep_warm;
                            next = prefs.keep_warm;
                            save_prefs(&state.prefs_file, &prefs);
                        }
                        log_line(&format!("[shell] keep-warm = {next}"));
                    }
                    "quit" => {
                        let state = app.state::<AppState>();
                        state.quitting.store(true, Ordering::SeqCst);
                        kill_tree(&state);
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_window(tray.app_handle());
                    }
                });

            if let Some(icon) = handle.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.build(&handle)?;

            // --- events from the app origin -------------------------------------
            // App commands are denied to remote origins, so the injected script
            // talks to us through core events (`core:default` includes emit).
            let notify_app = handle.clone();
            handle.listen("be-notify", move |event| {
                let payload = event.payload();
                match serde_json::from_str::<serde_json::Value>(payload) {
                    Ok(value) => {
                        let title = value
                            .get("title")
                            .and_then(|v| v.as_str())
                            .unwrap_or("Black Eclipse");
                        let body = value.get("body").and_then(|v| v.as_str()).unwrap_or("");
                        notify_native(&notify_app, title, body);
                    }
                    Err(err) => log_line(&format!("[notify] bad payload: {err}")),
                }
            });

            let window_app = handle.clone();
            handle.listen("be-window", move |event| {
                if let Ok(value) = serde_json::from_str::<serde_json::Value>(event.payload()) {
                    if let Some(action) = value.get("action").and_then(|v| v.as_str()) {
                        if action == "set-glass" {
                            let enabled = value
                                .get("enabled")
                                .and_then(|v| v.as_bool())
                                .unwrap_or(true);
                            set_window_glass(&window_app, enabled);
                        } else {
                            perform_window_action(&window_app, action);
                        }
                    }
                }
            });

            let shortcut_app = handle.clone();
            handle.listen("be-shortcut", move |event| {                let payload = event.payload();
                if let Ok(value) = serde_json::from_str::<serde_json::Value>(payload) {
                    match value.get("action").and_then(|v| v.as_str()) {
                        Some("fullscreen") => desktop_toggle_fullscreen(shortcut_app.clone()),
                        Some("devtools") => desktop_devtools(shortcut_app.clone()),
                        _ => {}
                    }
                }
            });

            // --- boot -------------------------------------------------------------
            start_supervisor(handle.clone());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build the Black Eclipse shell");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            let state = handle.state::<AppState>();
            if let Ok(prefs) = state.prefs.lock() {
                save_prefs(&state.prefs_file, &prefs);
            }
            kill_tree(&state);
        }
    });
}
