"""The Computer Use doctor.

Aggregates a human-readable, honest readiness report: platform, OS, display
server, accessibility/screen-capture permissions, driver availability/version,
input/window capability, OCR availability, vision availability, multi-monitor and
DPI. It never claims READY for a capability that is not actually present.
"""

from __future__ import annotations

import platform
import sys
from typing import Any, Optional


def _os_info() -> dict[str, Any]:
    info = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "platform": sys.platform,
    }
    if sys.platform.startswith("linux"):
        import os  # noqa: PLC0415

        info["displayServer"] = os.environ.get("WAYLAND_DISPLAY") and "wayland" or (
            os.environ.get("DISPLAY") and "x11" or "none"
        )
    return info


def diagnose(manager: Any) -> dict[str, Any]:
    """A structured readiness report for the Computer Use capability."""
    if manager is None:
        return {
            "status": "UNAVAILABLE",
            "reason": "the Computer Use runtime isn't available (Python runtime not started)",
            "os": _os_info(),
        }
    driver = manager.driver
    capabilities = driver.capabilities()
    contract = driver.contract()
    health = manager.health()

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("driver", driver.id != "null", f"{driver.label} ({driver.id})")
    add("accessibility", capabilities.accessibility, "UI Automation / AT-SPI / AX")
    add("screen_capture", capabilities.screen_capture, "screen capture")
    add("input_dispatch", capabilities.foreground_input or capabilities.background_input,
        "background" if capabilities.background_input else "foreground only")
    add("window_management", capabilities.window_management)
    add("application_management", capabilities.application_management)
    add("multi_monitor", capabilities.multi_monitor)
    add("ocr", capabilities.ocr or manager.ocr_available(), manager.ocr_description())
    add("vision", capabilities.vision or manager.vision_available(), manager.vision_description())

    ready = driver.id != "null" and (capabilities.foreground_input or capabilities.background_input)
    finance_ready = capabilities.finance_cua
    return {
        "status": "READY" if ready else "UNAVAILABLE",
        "os": _os_info(),
        "driver": {"id": driver.id, "label": driver.label, "health": health, "contract": contract.to_dict()},
        "capabilities": capabilities.to_dict(),
        "checks": checks,
        "financeCua": "Available" if finance_ready else "Unavailable",
        "notes": list(capabilities.notes),
        "reasons": [
            f"{c['name']} unavailable" for c in checks if not c["ok"]
        ],
    }


def format_report(report: dict[str, Any]) -> str:
    """A compact human-readable rendering of `diagnose`."""
    lines = [f"Computer Use: {report.get('status', 'UNKNOWN')}"]
    driver = report.get("driver", {})
    lines.append(f"Driver: {driver.get('label', '?')} [{driver.get('id', '?')}]")
    for check in report.get("checks", []):
        mark = "OK" if check["ok"] else "MISSING"
        detail = f" ({check['detail']})" if check.get("detail") else ""
        lines.append(f"  {check['name']}: {mark}{detail}")
    lines.append(f"Finance CUA: {report.get('financeCua', 'Unavailable')}")
    return "\n".join(lines)


__all__ = ["diagnose", "format_report"]
