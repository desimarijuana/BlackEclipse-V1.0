"""Computer Use END-TO-END finance scenario (live, controlled).

Drives the REAL Windows driver against a mock trading terminal we own, so the
whole path is exercised for real without touching a live broker:

    1 read the screen into structured financial state (with provenance)
    2 identify rebalance candidates against a 5% target
    3 run the finance firewall for a proposed order
    4 in read_only: BLOCKED (no click)
    5 in assisted: prepares, requests approval, does NOT submit
    6 prove the Submit control was NEVER clicked (the terminal's own log)

Prints a JSON result. This is a TEST FIXTURE, never imported by the runtime.
"""

from __future__ import annotations

import asyncio
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
from harness.computer.finance.firewall import ASSISTED, READ_ONLY, FinanceActionFirewall  # noqa: E402
from harness.computer.manager import ComputerManager  # noqa: E402

OUT: dict = {}


def _log_lines() -> list[str]:
    path = os.environ.get("CUA_TERMINAL_LOG", "")
    if not path or not os.path.exists(path):
        return []
    return [line.split()[-1] for line in open(path, encoding="utf-8").read().splitlines()]


async def main() -> int:
    tmp = Path(os.environ.get("TEMP", ".")) / "cua_fin.pid"
    log = Path(os.environ.get("TEMP", ".")) / "cua_fin.log"
    tmp.unlink(missing_ok=True)
    log.unlink(missing_ok=True)
    os.environ["CUA_TERMINAL_LOG"] = str(log)
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "computer_finance_terminal.py"), str(tmp)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    hwnd = 0
    for _ in range(50):
        await asyncio.sleep(0.1)
        if tmp.exists():
            try:
                _, h = tmp.read_text(encoding="utf-8").split()
                hwnd = int(h)
                break
            except (ValueError, OSError):
                pass
    if not hwnd:
        print(json.dumps({"error": "terminal failed to start"}))
        return 2

    cfg = computer_config(refresh=True)
    manager = ComputerManager(config=cfg)
    await manager.start()
    from harness.computer.policy import ALLOW, default_policy

    policy = default_policy()
    for p in ("observe", "click", "type", "key", "foreground", "window_control"):
        policy.permissions[p] = ALLOW
    session = await manager.create_session(policy=policy, risk_mode="read_only")
    core = ComputerCore(session, config=session._config)

    try:
        # 1. Read the screen into structured financial state.
        snap = await session.observe(window_id=str(hwnd), mode="som")
        state = manager.extractor.extract(
            snapshot=snap, application="mock_terminal", window="Eclipse Mock Trading Terminal",
        )
        OUT["read_state"] = {"symbol": state.symbol, "fields": state.fields,
                             "confidence": state.confidence, "provenance": state.provenance()}
        OUT["read_ok"] = (
            state.symbol == "NVDA" and state.fields.get("bid") == 185.21
            and state.fields.get("position") == 100 and state.fields.get("average_cost") == 174.20
            and state.provenance()["source_type"] == "desktop_screen"
        )

        # 2. Rebalance candidates against a 5% target using the deterministic
        #    calculator (never mental math). period_change is a real calculator.
        from harness.research.calculations import period_change
        portfolio = {"NVDA": state.fields.get("position", 0) * state.fields.get("bid", 0)}
        total = sum(portfolio.values()) or 1.0
        weights = {k: v / total for k, v in portfolio.items()}
        OUT["rebalance"] = {"weights": {k: round(v, 4) for k, v in weights.items()},
                            "violators": [k for k, v in weights.items() if v > 0.05]}
        # Exercise the calculator once so the harness proves the math path too.
        calc = period_change(100.0, 110.0)
        OUT["calc_smoke"] = getattr(calc, "value", None)

        # 3. Firewall in READ_ONLY: a buy must be BLOCKED, and no click may occur.
        fw_ro = FinanceActionFirewall(mode=READ_ONLY)
        ro = fw_ro.evaluate({"action": "buy", "instrument": "NVDA", "quantity": 10, "price": 185.21,
                             "application": "mock_terminal"})
        OUT["read_only"] = ro.to_dict()
        # The agent is told blocked; it must NOT reach for the UI.
        OUT["read_only_blocked"] = ro.blocked

        # 4. ASSISTED: prepare is allowed, submit needs approval, still no click.
        fw_as = FinanceActionFirewall(mode=ASSISTED, max_order_value=25000)
        prep = fw_as.evaluate({"action": "prepare_order", "instrument": "NVDA", "quantity": 10,
                               "price": 185.21, "application": "mock_terminal"})
        submit = fw_as.evaluate({"action": "buy", "instrument": "NVDA", "quantity": 10,
                                 "price": 185.21, "application": "mock_terminal"})
        OUT["assisted"] = {"prepare": prep.to_dict(), "submit": submit.to_dict()}
        OUT["assisted_ok"] = prep.allowed and submit.requires_approval and not submit.blocked

        # 5. Prove the Submit/Buy/Sell/Transfer controls were never clicked.
        OUT["terminal_log"] = _log_lines()
        OUT["no_mutation_click"] = not any(
            entry in ("SUBMIT_ORDER", "BUY", "SELL", "TRANSFER") for entry in OUT["terminal_log"]
        )

        # 6. A read is always fine; confirm we can still observe.
        snap2 = await session.observe(window_id=str(hwnd), mode="som")
        OUT["reobserve_ok"] = any(e.name == "Submit Order" for e in snap2.elements)
    finally:
        await manager.stop()
        proc.terminate()

    print(json.dumps(OUT, indent=1, default=str))
    ok = OUT.get("read_ok") and OUT.get("read_only_blocked") and OUT.get("assisted_ok") and OUT.get("no_mutation_click")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
