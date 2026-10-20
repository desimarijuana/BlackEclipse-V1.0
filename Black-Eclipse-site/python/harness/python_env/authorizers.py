"""Single-use operator approval for package installs and removals."""

from __future__ import annotations

import hashlib
from typing import Any

from .provisioner import normalize_specs

INSTALL_KIND = "python_env_install"
REMOVE_KIND = "python_env_remove"
REQUEST_KEY = "python_env"


def _digest(kind: str, values: list[str]) -> str:
    return hashlib.sha256(
        (kind + "\x00" + "\x00".join(values)).encode("utf-8")
    ).hexdigest()


def make_python_env_authorizer(inner: Any = None):
    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name not in (INSTALL_KIND, REMOVE_KIND):
            return bool(await inner(tool, args, ctx)) if inner is not None else False

        run_args = args or {}
        packages = run_args.get("packages") or []
        if not isinstance(packages, list):
            return False
        if name == INSTALL_KIND:
            cleaned, error = normalize_specs(packages)
            if error or not cleaned:
                return False
            kind = INSTALL_KIND
            digest = _digest(kind, cleaned)
            summary = "Install Python packages into the analysis environment: " + ", ".join(cleaned)
            effect, risk = "external_action", "medium"
            payload = {"packages": cleaned}
            title = "Approve installing Python packages"
        else:
            cleaned = [str(item or "").strip() for item in packages if str(item or "").strip()]
            if not cleaned:
                return False
            kind = REMOVE_KIND
            digest = _digest(kind, sorted(cleaned))
            summary = "Remove Python packages from the analysis environment: " + ", ".join(cleaned)
            effect, risk = "write", "low"
            payload = {"packages": cleaned}
            title = "Approve removing Python packages"

        approvals = getattr(ctx, "approvals", None) if ctx is not None else None
        if approvals is None:
            return False
        claimed = approvals.consume_kind(kind=kind, request_key=REQUEST_KEY, digest=digest)
        if claimed is not None:
            return True
        pending = None
        try:
            pending = approvals.request_kind(
                kind=kind, request_key=REQUEST_KEY, digest=digest,
                effect=effect, run_id=str(getattr(ctx, "run_id", "")),
                action_summary=summary, affected_data=payload, risk=risk,
            )
        except Exception:  # noqa: BLE001 - a store failure must never authorize
            return False
        emitter = getattr(ctx, "emitter", None)
        if emitter is not None:
            try:
                await emitter.emit("approval.requested", {
                    "approvalId": (pending or {}).get("id"),
                    "kind": kind, "title": title, "summary": summary,
                    "effect": effect, "risk": risk, **payload,
                })
            except Exception:  # noqa: BLE001 - the card is best-effort
                pass
        if pending is not None:
            from ..mcp.approvals import pause_for_decision  # noqa: PLC0415

            if await pause_for_decision(
                approvals, ctx, pending.get("id"),
                lambda: approvals.consume_kind(kind=kind, request_key=REQUEST_KEY, digest=digest),
                emitter=emitter, digest=digest,
                event_type="approval.approved",
                approved_payload={"kind": kind, **payload},
            ):
                return True
        return False

    return authorize


__all__ = ["INSTALL_KIND", "REMOVE_KIND", "REQUEST_KEY", "make_python_env_authorizer"]
