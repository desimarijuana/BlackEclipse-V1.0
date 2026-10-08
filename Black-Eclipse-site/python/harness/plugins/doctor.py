"""Plugin doctor — a diagnostic that returns actionable remediation.

Every check is deterministic and read-only. Each result carries `ok`, a short
`detail`, and (when not ok) a `remediation` a person can act on. Nothing here
contacts the network on its own; the manager may optionally pass connectivity
results in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .manifest import ECLIPSE_VERSION


def _check(name: str, ok: bool, detail: str, remediation: str = "") -> dict[str, Any]:
    return {"check": name, "ok": ok, "detail": detail, "remediation": remediation}


def diagnose(manager: Any, plugin_id: str, *, connectivity: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    record = manager.store.get_plugin(plugin_id)
    if record is None:
        return {"ok": False, "pluginId": plugin_id, "checks": [
            _check("installed", False, "plugin is not installed", "install the plugin first"),
        ], "summary": "not installed"}

    checks: list[dict[str, Any]] = []
    manifest = manager.manifest_of(plugin_id)
    checks.append(_check("manifest", manifest is not None, "manifest parsed" if manifest else "manifest missing/corrupt",
                         "reinstall the plugin from a valid source"))

    path = manager.path_of(plugin_id)
    exists = bool(path and Path(path).exists())
    checks.append(_check("installation", exists, f"path {path}" if exists else "installation path missing",
                         "reinstall or repair the plugin"))

    integrity = manager.check_integrity(plugin_id)
    checks.append(_check("integrity", integrity.get("ok", False),
                         f"checksum {integrity.get('detail', '')}",
                         "the installed files changed; repair or reinstall"))

    deps = manager.dependency_status(plugin_id)
    missing = [d["id"] for d in deps if not d.get("satisfied") and not d.get("optional")]
    checks.append(_check("dependencies", not missing,
                         "all required dependencies present" if not missing else f"missing: {', '.join(missing)}",
                         "install the missing dependencies"))

    if manifest is not None:
        reason = manifest.check_eclipse_version(ECLIPSE_VERSION)
        checks.append(_check("compatibility", reason is None, reason or f"compatible with Eclipse {ECLIPSE_VERSION}",
                             "update the plugin or the host"))

    granted = manager.granted_permissions(plugin_id)
    elevated_needed = [p for p in record.permissions if p in manager.elevated_permissions()]
    not_granted = [p for p in elevated_needed if p not in granted]
    checks.append(_check("permissions", not not_granted,
                         "all declared permissions granted" if not not_granted
                         else f"not granted: {', '.join(not_granted)}",
                         "enable the plugin as an operator to grant elevated permissions"))

    if manifest is not None and manifest.authentication.type != "none":
        present = manager.authentication_ready(plugin_id)
        checks.append(_check("authentication", present,
                             "credentials present" if present else "no credentials configured",
                             f"run `eclipse plugin auth {plugin_id}` or set the required secrets"))

    loaded = manager.is_active(plugin_id)
    checks.append(_check("runtime", loaded,
                         "runtime loaded" if loaded else f"state {record.status.value}",
                         "enable the plugin" if not loaded else ""))

    contributions = manager.contribution_descriptors(plugin_id)
    checks.append(_check("contributions", bool(contributions) or manifest is None,
                         f"{len(contributions)} contribution(s) registered",
                         "reload the plugin if contributions are missing"))

    health = manager.health_report(plugin_id)
    checks.append(_check("health", health.get("status") not in ("unhealthy",),
                         f"health={health.get('status')}",
                         "inspect logs with `eclipse plugin logs {0}`".format(plugin_id)))

    if connectivity:
        checks.append(_check("connectivity", bool(connectivity.get("ok")),
                             connectivity.get("detail", "unknown"),
                             connectivity.get("remediation", "")))

    ok = all(c["ok"] for c in checks)
    return {
        "ok": ok,
        "pluginId": plugin_id,
        "checks": checks,
        "summary": "all checks passed" if ok else "; ".join(c["detail"] for c in checks if not c["ok"]),
        "log": manager.logs(plugin_id, limit=20),
    }


__all__ = ["diagnose"]
