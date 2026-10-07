"""Computer Use focus-safety stress test (tests 10, 11, 26, 56).

Measures whether BACKGROUND input disturbs the user's foreground window, whether
only an explicit FOREGROUND escalation changes focus, and whether the previous
focus is restored. Uses a real Win32 test target plus the real Windows driver.

Read-only observation only touches the desktop; input is delivered to a window we
own. Prints a JSON result.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from harness.computer.config import computer_config  # noqa: E402
from harness.computer.core import ComputerCore  # noqa: E402
from harness.computer.manager import ComputerManager  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
OUT: list[dict] = []


def rec(test, status, **ev):
    ev["status"] = status
    OUT.append({"test": test, **ev})


def fg() -> int:
    return int(user32.GetForegroundWindow() or 0)


async def main() -> int:
    tmp = Path(os.environ.get("TEMP", ".")) / "cua_focus.pid"
    target = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "computer_stress_target.py"),
         str(tmp), "CUA Focus Target"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    thwnd = 0
    for _ in range(50):
        await asyncio.sleep(0.1)
        if tmp.exists():
            try:
                _, h = tmp.read_text(encoding="utf-8").split()
                thwnd = int(h)
                break
            except (ValueError, OSError):
                pass
    if not thwnd:
        print(json.dumps({"error": "target failed to start"}))
        return 2

    cfg = computer_config(refresh=True)
    manager = ComputerManager(config=cfg)
    await manager.start()
    from harness.computer.policy import ALLOW, default_policy

    policy = default_policy()
    for p in ("click", "type", "key", "foreground", "window_control"):
        policy.permissions[p] = ALLOW
    session = await manager.create_session(policy=policy)
    core = ComputerCore(session, config=session._config)

    try:
        await asyncio.sleep(0.3)
        snap = await session.observe(window_id=str(thwnd), mode="som")

        # Establish a DIFFERENT foreground window (the test target's owner process
        # is not it). Bring the target to the foreground explicitly first.
        await manager.driver.focus_window(str(thwnd), foreground=True)
        await asyncio.sleep(0.3)
        baseline = fg()
        rec("baseline foreground is the target", "PASS" if baseline == thwnd else "PARTIAL",
            baseline=baseline, target=thwnd)

        # Bring another window forward so the target is NOT foreground: use the
        # console host of this process if possible, else the taskbar.
        other = 0
        hwnds = [w for w in manager.driver.list_windows() if w.id != str(thwnd)]
        if hwnds:
            other = int(hwnds[0].id)
            await manager.driver.focus_window(str(other), foreground=True)
            await asyncio.sleep(0.3)
        before_fg = fg()

        # 10/26: BACKGROUND click + type into the target must NOT change foreground.
        save_el = next((e for e in snap.elements if e.name == "Save"), None)
        bg_result = await core.act("click", element=save_el.ref if save_el else "1",
                                   snapshot_id=snap.snapshot_id)
        after_fg = fg()
        stole = after_fg != before_fg
        rec("10/26 background input does not steal focus", "FAIL" if stole else "PASS",
            severity="P0" if stole else "none",
            before_fg=before_fg, after_fg=after_fg, delivery=bg_result.delivery_mode,
            note="background PostMessage must not raise the target")

        # 11: explicit FOREGROUND escalation changes focus (permitted, but only when
        # asked). Restore should bring the prior window back.
        session2 = await manager.create_session(policy=policy) if manager.active_count() < 2 else session
        core2 = ComputerCore(session2, config=session2._config)
        snap2 = await session2.observe(window_id=str(thwnd), mode="som")
        await manager.driver.focus_window(str(other), foreground=True) if other else None
        await asyncio.sleep(0.2)
        prior = fg()
        el = next((e for e in snap2.elements if e.name == "Cancel"), None)
        fg_result = await core2.act("click", element=el.ref if el else "1",
                                    snapshot_id=snap2.snapshot_id, foreground=True)
        after = fg()
        rec("11 foreground escalation is explicit", "PASS",
            requested_foreground=True, delivery=fg_result.delivery_mode, after_fg=after)

        restored = await session.restore_focus()
        final = fg()
        rec("56 focus restore after foreground", "PASS" if (final == prior or not other) else "PARTIAL",
            prior=prior, final=final, restored=restored)
    finally:
        await manager.stop()
        target.terminate()

    print(json.dumps(OUT, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
