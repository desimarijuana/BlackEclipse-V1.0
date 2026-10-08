---
title: Computer Use Engine
status: Current
last-verified: 2026-10-07
---

# Computer Use Engine

**Who this is for:** anyone extending Eclipse's desktop-control capability, or
debugging a run that drove a native application.

> Deciding whether a task belongs here, in the web-research engine, or in the
> browser? See [`research-surfaces.md`](./research-surfaces.md) — the one "which
> surface answers which question" page.

The **Computer Use Engine** (`python/harness/computer/`) lets Eclipse observe and
operate a real desktop: native applications (Excel, VS Code, a terminal
*emulator*, PDF readers), OS chrome (file pickers, dialogs, menus) and financial
terminals (TradingView, MetaTrader 5, Interactive Brokers, Bloomberg-style). It is
a first-class capability registered on the **same** `ToolRegistry`, gated by the
**same** permission/approval architecture, persisted on the **same**
`agent-memory.db`, and observable on the **same** event bus. It is not a parallel
stack.

## The fundamental loop

```
OBSERVE → UNDERSTAND → PLAN → GROUND → AUTHORIZE → ACT → OBSERVE → VERIFY
        → (SUCCESS | RECOVER → REPLAN)
```

Every important action carries state awareness and verification. A result hands
back a **verdict** (`success`, `recapture`, `retry`, `reground`,
`foreground_required`, `approval_required`, `blocked`, `ask_user`, `abort`) so the
agent follows a directive instead of guessing.

## Computer Use vs the browser subsystem

They are **different systems that coexist**:

| | Browser (`harness/browser/`) | Computer Use (`harness/computer/`) |
|---|---|---|
| Owns | DOM, HTML, page nav, forms, browser content | native apps, OS UI, dialogs, file pickers, app chrome, browser *chrome* |
| Observation | accessibility snapshot (`@eN`) | SOM (`#N`) from the AX tree, OCR, vision |
| Use it for | web pages | anything outside a page's DOM |

The browser is **not** replaced by Computer Use, and vice versa. Browser *chrome*
(address bar, permission dialogs, extension popups) belongs to Computer Use.

## Layer map

| Module | Owns |
|---|---|
| `core.py` | the platform-independent orchestrator (`ComputerCore`): the ONE loop; delivery-mode escalation; finance routing |
| `manager.py` | the process-wide `ComputerManager` (sessions, driver, engines, leases, store) |
| `session.py` | one `ComputerSession`: state, snapshot cache, stale-handle validation, focus restore |
| `drivers/` | `ComputerDriver` interface + `windows.py` (ctypes Win32), `linux.py` (ctypes X11/XTest), `macos.py` (ctypes Core Graphics/AX), `wayland.py` (grim/ydotool), `window.py` (attach to a contained remote/isolated desktop) + `null.py`; the factory picks the platform driver |
| `accessibility/` | AX providers: `windows.py` (UIA when installed, Win32 child-window baseline), `linux.py` (AT-SPI), `macos.py` (AX API), `null.py` |
| `observation.py` | builds a `Snapshot` in mode `som`/`ax`/`ocr`/`vision`; mints snapshot ids + numbered handles |
| `grounding/` | `Grounder` (the fixed hierarchy) + pure matchers |
| `actions/` | `mouse.py`, `keyboard.py`, `value.py` (`set_value`), `keymap.py` (semantic shortcuts) |
| `windows/` · `applications/` | window management; application management + the `ApplicationAdapter` framework and initial adapters |
| `screenshots/` | capture + region intelligence + screen diff |
| `ocr/` | first-class OCR (`windows.py` OS-native via `winsdk`; Tesseract; honest null otherwise) |
| `vision/` | provider-agnostic vision via the harness model runtime; local/cloud/hybrid routing |
| `verification/` | `ActionVerifier` (verified / failed / uncertain) |
| `recovery.py` | the recovery ladder + `RecoveryEngine` |
| `policy.py` · `security.py` | permission engine + risk bands; sensitive-region detection/redaction; challenge + injection detection |
| `finance/` | field vocabulary, screen extraction (with provenance), the **Finance Action Firewall** |
| `takeover.py` · `broker.py` | the per-session control lease; the machine-wide session broker |
| `desktop.py` | `DesktopProvisioner` (local shared; real Xvfb, RDP, Windows Sandbox; Wayland attach) — create/attach/teardown of a session's desktop |
| `recording.py` · `replay.py` | trajectories + deterministic replay |
| `telemetry.py` · `diagnostics.py` | metrics; the doctor |
| `store.py` · `memory.py` | `agent-memory.db` tables; Eclipse-Memory knowledge (not JDdS) |
| `schemas.py` · `tools.py` | `computer_*` model-facing toolset |
| `routers/computer.py` | the operator HTTP surface |

## Stable element handles + stale protection

Every `capture` mints a `snapshot_id` and a generation. An element handle
(`#N`) is only valid against the snapshot it came from. An action that passes an
`element` (and its `snapshot_id`) is validated for snapshot, window, application
and identity; a mismatch returns `COMPUTER_STALE_ELEMENT` (verdict `recapture`)
and the model must re-capture. An old element number is **never** silently mapped
to a new UI element.

## Grounding hierarchy

```
1 accessibility element → 2 semantic → 3 structured UI → 4 OCR → 5 vision
→ 6 relative coordinate → 7 raw coordinate
```

Coordinates are the fallback. High-risk targets require a fresh semantic target,
a fresh observation and policy approval.

## Background-first delivery

Default delivery is **background**: input is posted directly to the target
window and the user's cursor, focus and virtual desktop are not disturbed. A
`foreground` escalation (SendInput; raises/focuses) is explicit, counted in
telemetry, and the previous focus is restored afterwards. A background attempt
that produces no change escalates **once** — never silently, never in a loop.

Two guarantees make this safe on Windows:

- A background click is posted to the **deepest child control under the point**
  (`RealChildWindowFromPoint`, z-order independent) with **client** coordinates;
  a message sent to the top-level window alone would never activate a child
  control. Background keyboard input targets the owning thread's focused control
  (`GetGUIThreadInfo`).
- A **foreground** absolute-coordinate click is refused when the point is owned
  by a different top-level window (`COMPUTER_TARGET_OBSCURED`, verdict
  `foreground_required`) — Eclipse never clicks blind into a covering window, and
  never sends foreground keystrokes to a window that is not focused.

Verification reads a **fresh** accessibility digest + window title (never the
pre-action snapshot), settle-polls for a bounded window, and treats only
*content* change as `verified`; incidental pixel churn is `uncertain`, and an
`uncertain` result never becomes a `success` verdict.

Background-first delivery covers clicks, typing, keys, **pointer moves, scrolls,
drags and button press/release**: each posts the corresponding `WM_*` message to
the control under the point in the target's own child hierarchy, so none of them
need steal the user's focus. `mouse_move`/`scroll`/`drag` follow the configured
`mode` and may still be forced `foreground`.

Observation also scans for **sensitive** controls/text: a sensitive snapshot is
flagged, its persisted image is masked, and a cloud vision model is refused
unless policy explicitly allows it. An unrelated dialog that appears after an
action is reported as `UNEXPECTED_DIALOG` (verdict `ask_user`) instead of
receiving blind input. A **CAPTCHA / MFA / biometric / security challenge**
(detected from the foreground window or screen text via
`security.detect_challenge`) is a hard stop: the core refuses *before* delivering
any input and returns `COMPUTER_HUMAN_REQUIRED` (verdict `ask_user`) so a person
takes over — Eclipse never tries to solve or bypass it.

**Limits are enforced, not just advertised.** Every action runs under a
per-action timeout (`action_timeout_seconds`; breach ⇒ `COMPUTER_TIMEOUT`,
verdict `retry`) and a hard session budget (`max_actions`; breach ⇒
`BudgetExceeded`/`COMPUTER_BUDGET_EXCEEDED`, verdict `abort`). A dry run still
counts against the budget, matching what `capabilities().limits` reports.

## Isolated desktops

`desktop.py` decides WHERE a session runs. `isolation.mode=off` (default) uses the
shared local desktop; `auto`/`on` provisions an isolated one, falling back to local
with a reason if the backend is absent. `headless_desktop` is true only for a
genuinely provisioned isolated desktop.

| Provider | Backend | Isolated | Status |
|---|---|---|---|
| `local` | the operator's desktop | no | default; sessions serialize via `broker.py` |
| `x11` | private `Xvfb :N` per session | yes | **real** — create/attach/teardown, tested |
| `rdp` | `mstsc` to `rdp.host`/`rdp.file` | yes | **real** — attaches a `WindowDriver` to the client window |
| `windows_sandbox` | `WindowsSandbox.exe` guest window | yes | **real** — attaches to the sandbox client window |
| `wayland` | nested headless compositor (`wlheadless-run`/`sway`/`weston`) | yes | **real** — private socket; `grim` capture + `ydotool` input |

- **`WindowDriver`** (`drivers/window.py`) is the attach mechanism for remote/isolated
  desktops: it scopes capture/input to the contained desktop window and translates
  window-local coordinates to absolute foreground events. Input is **background-first
  when the base driver supports it**, escalating to foreground (with verification)
  otherwise. Because the guest's native accessibility tree is not host-visible, the
  driver derives a real element tree from **OCR of the contained window**
  (`source=ocr`); with no OCR backend it reports `accessibility:false` honestly.
- An **isolated session does not take the machine-wide broker**, so N agents run
  concurrently on N desktops; shared sessions still serialize.
- **`WaylandDriver`** (`drivers/wayland.py`) reports capture and input separately:
  a missing `grim` makes capture False, a missing `ydotool` makes input False —
  each with a reason. `WaylandHeadlessProvisioner` gives a session its own headless
  compositor socket when a launcher/compositor is installed.

## Security, permissions, finance

- The **policy engine** (`policy.py`) is the ONE permission authority:
  `READ`/`LOW`/`MEDIUM`/`HIGH`/`CRITICAL` risk bands, an application
  allow/deny/prohibit policy, and fail-closed defaults (observe allowed; click/
  type ASK; `finance_mutate` DENY). An ASK routes through the same single-use
  approval store the rest of the harness uses.
- The **security layer** flags sensitive UI (password/API key/seed phrase/2FA/
  bank credentials) and masks regions before a frame leaves the machine or enters
  an exportable trajectory. A sensitive frame is never sent to a cloud vision
  model unless policy explicitly allows it.
- The **Finance Action Firewall** (`finance/firewall.py`) classifies and gates
  every financial intent. Modes: `read_only`, `assisted`, `autonomous`,
  `simulation`. `transfer`/`withdraw`/`deposit`/`payment`/`account_change` are
  always blocked; a live mutation needs approval; `assisted` may prepare but not
  submit; notional/account/instrument/app allowlists are enforced **before** the
  UI is touched.
- Screen-derived finance carries explicit provenance
  (`source_type=desktop_screen`) and is never authoritative market data.

## Integration

- **Tools:** `register_computer_tools` registers the `computer_*` set on the one
  registry (in `service.py`, beside the browser/terminal/git tools). The elevated
  half (`COMPUTER_EFFECTFUL_TOOLS` in `code/policy.py`) is removed at `plan_only`;
  `computer_use` stays (like `browser_click`) and is gated per-call.
- **Authorizer:** `computer/authorizers.py` is composed into the ONE chain in
  `code/authorizers.py`.
- **Agents:** `COMPUTER_TOOLS` is declared once in `agents.py` and offered to the
  finance agent, the code agent and the chat code profile.
- **HTTP:** `routers/computer.py` (`/computer/*`, operator-gated) is included by
  `main.py`; lifespan calls `service.start_computer()` / `stop_computer()`.
- **CLI:** `eclipse computer doctor|status|capabilities|windows|apps|displays|sessions|replay`.
- **Memory:** `computer/memory.py` stores learned layouts/workflows/recovery paths
  in `eclipse-memory` (never JDdS, never screenshots), only through the explicit
  `computer_remember` tool.
- **Human hand-off:** `computer_takeover` (and `computer_request_human` for a
  challenge) hand the control lease to a person; the agent stops, state is
  preserved, and `computer_resume`/`computer_release` return control.

## Configuration

`computer/config.py` resolves defaults ← `.black-eclipse/computer.json` ← env
(`HARNESS_COMPUTER_*`). A reference file is committed at `computer.example.json`.
Notable keys now wired end-to-end: `vision.model` (overrides the resolved vision
model id), `ocr.enabled` (disables OCR entirely) and `ocr.backend`
(`auto|winocr|tesseract|none`), the finance allowlists
`finance.allowed_apps|allowed_accounts|allowed_instruments`
(`HARNESS_COMPUTER_FINANCE_ALLOWED_*`), and desktop isolation
`isolation.mode` (`off|auto|on`), `isolation.provider`
(`auto|local|x11|wayland|windows_sandbox|rdp`), `isolation.display_base`,
`isolation.screen`, `isolation.rdp_host`, `isolation.rdp_file`
(`HARNESS_COMPUTER_ISOLATION`, `HARNESS_COMPUTER_ISOLATION_PROVIDER`,
`HARNESS_COMPUTER_DISPLAY_BASE`, `HARNESS_COMPUTER_RDP_HOST`, `HARNESS_COMPUTER_RDP_FILE`).

## Honesty (nothing is fabricated)

A missing driver, accessibility backend, OCR engine or vision model is an honest
`UNAVAILABLE` with a reason — never a fake desktop. `eclipse computer doctor`
reports exactly what is present. On Windows the driver uses `ctypes` Win32 (no
third-party package required). `auto` OCR prefers the OS-native engine
(`Windows.Media.Ocr` via `winsdk`), then Tesseract; the rich accessibility tree
(UIA via `uiautomation`) and the native OCR are optional and their absence is
reported, not hidden. `Pillow`/`uiautomation`/`winsdk` are declared in
`requirements.txt` and installed/repaired by `setup-python.js`/`doctor.js`.

## Platform support and roadmap

| Platform | Driver | Input | Accessibility | Status |
|---|---|---|---|---|
| Windows | `windows.py` (ctypes Win32) | foreground (SendInput) + background (PostMessage) | UIA (installed) / Win32 baseline | **Ready** |
| Linux/X11 | `linux.py` (ctypes X11/XTest) | foreground (XTest) | AT-SPI (if `python3-pyatspi`) | Implemented; live-verification pending |
| macOS | `macos.py` (ctypes CGEvent/AX) | foreground (CGEvent) | AX API (Accessibility TCC) | Implemented; TCC permissions required |
| Linux/Wayland | — | — | — | Honest `NullDriver` (no global-input API) |

The driver factory returns a real driver per platform and a genuine `NullDriver`
where no backend exists (Wayland-only sessions without `grim`/`ydotool`, unknown
OS). Isolated desktops are covered above. Remaining honest gaps:

- **Live app verification** (`tests/test_computer_apps_live.py`, opt-in via
  `BLACK_ECLIPSE_CUA_APPS=1`) drives real apps; adapters carry a `verified` flag
  that defaults False (knowledge record) until a live run marks it with a build note.
- **Xvfb** has an opt-in live test (`tests/test_computer_xvfb_live.py`,
  `BLACK_ECLIPSE_CUA_XVFB=1` on Linux) — the injected-probe lifecycle runs everywhere,
  the real capture runs on a Linux host.
- **Sandbox/RDP input** is best-effort: background-first where the base driver
  supports it, else foreground with verification; a client may still not forward
  every event. The guest element tree is OCR-derived, not native AX.

## Tests

`python/tests/test_computer_unit.py` (pure logic), `test_computer_safety.py`
(finance firewall, approval boundary, stale protection, takeover, dry-run),
`test_computer_tools.py` (the toolset over a deterministic fake driver),
`test_computer_adversarial.py` (moved/duplicate/absent targets, DPI, finance
adversarial matrix) and `test_computer_hardening.py` (the defects found by the
production stress test — background child-control delivery, occlusion refusal,
semantic verification, sensitive wiring, action allowlist, recovery plan,
bounded `set_value`, cross-session snapshot ids, memory source).

The **live stress rig** (`python/tests/computer_stress_rig.py`,
`computer_stress_target.py`, `computer_stress_focus.py`) drives the REAL Windows
driver against a controlled Win32 window our test target owns, so it exercises
the actual input path without disturbing the live desktop. It covers observation,
stale handles, UI change, grounding, verification, input, recovery, freeze/race,
the finance firewall matrix, takeover, sensitive data, audit/replay/memory,
latency, session isolation, failure injection, prompt injection and focus-safety.

Additional production harnesses:

- **`test_computer_demos.py`** — the demo workflows (locate/read, find-and-click,
  set-value-and-verify, read financial state, prepare-never-submit) run against
  owned Win32 windows with the real driver.
- **`test_computer_benchmark.py`** — the Eclipse CUA Benchmark: grounding
  accuracy, verification accuracy, recovery success, task completion, and the
  finance priority (`false_action_rate_read_only`, `dangerous_action_rate`,
  `noop_false_success_rate`), each asserted at its production bar.
- **`computer_finance_e2e.py`** + **`computer_finance_terminal.py`** — a full
  finance scenario on a mock trading terminal: screen-derived state with
  provenance, a deterministic rebalance calc, and proof (from the terminal's own
  click log) that read_only blocks, assisted holds for approval, and no mutation
  control is ever clicked.

## High-risk target gate

A CRITICAL action (a financial mutation, or a Submit/Buy/Sell/Transfer control an
adapter flags risky) is held to a stricter standard than a normal click:
`ComputerCore` refuses a **coordinate-only** target or a target whose confidence
is below the floor, and requires the target to be grounded against the CURRENT
snapshot. A caller can override only by passing BOTH `allow_coordinates=true` and
`confirm_coordinates=true`. Coordinates are never the primary method for a
critical action.
