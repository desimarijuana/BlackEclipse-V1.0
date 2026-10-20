"""Build, test and activate a generated capability."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Optional

from ..code.execution import IMPORT_ALLOWLIST
from .handoff import plan_handoff
from .manifest import CapabilityManifest, CapabilityPort, PURE_KINDS
from .registry import (
    draft_root,
    global_root,
    refresh_generated_recipes,
    register,
    remove_generated_recipe,
)
from .request import CapabilityRequest, classify, slug_for
from .store import CapabilityRecord, CapabilityStore
from .verifier import VerificationReport, digest_text, verify


def _default_root() -> Optional[Path]:
    try:
        from ..code.workspace import default_root

        return default_root()
    except Exception:
        return None


def _infer_kind(value: Any) -> str:
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return "table"
        return "series"
    if isinstance(value, dict):
        return "table"
    return "scalar"


def _infer_inputs(samples: dict[str, Any]) -> list[CapabilityPort]:
    return [
        CapabilityPort(name=name, kind=_infer_kind(value), required=True)
        for name, value in samples.items()
        if str(name).isidentifier()
    ]


def _infer_imports(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in IMPORT_ALLOWLIST and top not in names:
                    names.append(top)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in IMPORT_ALLOWLIST and top not in names:
                names.append(top)
    return names


def _safe_component(value: str) -> str:
    cleaned = "".join(ch for ch in str(value) if ch.isalnum() or ch in "._-")
    return cleaned or "draft"


def _target_dir(root: Path, capability_id: str, version: str) -> Path:
    base = draft_root(root)
    target = base / _safe_component(capability_id) / _safe_component(version)
    target.resolve().relative_to(base.resolve())
    return target


def _path_inside(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except (OSError, ValueError):
        return False


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _readme(manifest: CapabilityManifest, request: CapabilityRequest) -> str:
    inputs = "\n".join(
        f"- `{port.name}` ({port.kind}, {'required' if port.required else 'optional'})"
        for port in manifest.inputs
    ) or "- none"
    outputs = "\n".join(
        f"- `{port.name}` ({port.kind})" for port in manifest.outputs
    ) or "- declared by the program's `result`"
    acceptance = manifest.acceptance or request.need
    return (
        f"# {manifest.title}\n\n"
        f"{manifest.description}\n\n"
        f"Status: {manifest.scope} generated capability, version {manifest.version}.\n\n"
        f"## Inputs\n\n{inputs}\n\n"
        f"## Outputs\n\n{outputs}\n\n"
        f"## Acceptance\n\n{acceptance}\n\n"
        f"## Test\n\n"
        f"`test_capability.py` is a contract fragment. The verifier prepends "
        f"`capability.py` and runs the combined program in the analysis sandbox.\n\n"
        f"## Use\n\n"
        f"Call `analysis_run` with `recipe=\"{manifest.id}\"` and the inputs above. "
        f"The result is computed in the Eclipse sandbox and labelled computed.\n"
    )


def _manifest_for(request: CapabilityRequest, kind: str, version: str) -> CapabilityManifest:
    inputs = list(request.inputs) or _infer_inputs(request.sample_inputs)
    imports = list(request.imports) or _infer_imports(request.implementation)
    acceptance = " ".join(item for item in request.acceptance if item).strip()
    if not acceptance:
        acceptance = "The contract test passes in the Eclipse sandbox."
    return CapabilityManifest(
        id=slug_for(request.need, request.capability_id),
        version=version,
        kind=kind,
        title=request.need.strip()[:120],
        description=(request.evidence or request.need).strip()[:600],
        scope=request.scope if request.scope in ("workspace", "global") else "workspace",
        inputs=inputs,
        outputs=list(request.outputs),
        permissions=list(request.permissions) or ["analysis.execute"],
        effect="read",
        timeout_ms=request.timeout_ms,
        imports=imports,
        tests=["test_capability.py"],
        acceptance=acceptance[:1_000],
    )


def _record(
    manifest: CapabilityManifest,
    report: VerificationReport,
    directory: Path,
    status: str,
    run_id: Optional[str],
    task_id: Optional[str] = None,
) -> CapabilityRecord:
    return CapabilityRecord(
        capability_id=manifest.id,
        version=manifest.version,
        kind=manifest.kind,
        title=manifest.title,
        description=manifest.description,
        scope=manifest.scope,
        status=status,
        manifest=manifest.to_dict(),
        source_digest=report.source_digest,
        test_digest=report.test_digest,
        test_status=report.status,
        tests=list(manifest.tests),
        directory=str(directory),
        run_id=run_id,
        task_id=task_id or None,
    )


def _failure(status: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, **extra}


def build(
    request: CapabilityRequest,
    *,
    store: CapabilityStore,
    root: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> dict[str, Any]:
    kind = classify(request.need, request.kind)
    if kind == "one_off":
        return _failure(
            "one_off",
            "this is a one-off computation; use analysis_run and persist nothing",
            nextTool="analysis_run",
        )
    if kind not in PURE_KINDS:
        handoff = plan_handoff(request, kind=kind)
        handoff.resume["taskId"] = request.resume_task_id or None
        request.handoff = handoff.to_dict()
        store.save_request(request, status="handoff_required")
        return {
            "status": "handoff_required",
            "capabilityId": slug_for(request.need, request.capability_id),
            "surface": handoff.surface,
            "nextTool": handoff.next_tool,
            "handoff": handoff.to_dict(),
            "activation": handoff.activation,
            "requiresApproval": handoff.requires_approval,
            "reason": handoff.verification,
        }

    base = Path(root) if root is not None else _default_root()
    if base is None:
        return _failure("refused", "there is no workspace to build the capability in", code="WORKSPACE_UNAVAILABLE")

    source = request.implementation or ""
    if not source.strip():
        return _failure(
            "needs_source",
            "the capability needs a short implementation program before it can be built",
            missing=["implementation source"],
        )

    capability_id = slug_for(request.need, request.capability_id)
    existing = store.get(capability_id)
    if existing is not None and not request.version:
        version = store.next_version(capability_id)
    elif request.version:
        version = request.version
    else:
        version = "1.0.0"

    previous = store.get(capability_id, version)
    if (
        previous is not None
        and previous.get("sourceDigest") == digest_text(source)
        and previous.get("testDigest") == digest_text(request.test or "")
    ):
        return {
            "status": previous.get("status"),
            "capabilityId": capability_id,
            "version": version,
            "activated": previous.get("status") == "active",
            "idempotent": True,
            "record": previous,
        }

    try:
        manifest = _manifest_for(request, kind, version)
    except Exception as exc:
        return _failure("refused", f"the capability manifest is invalid: {exc}", code="MANIFEST_INVALID")

    try:
        directory = _target_dir(base, capability_id, version)
    except (OSError, ValueError):
        return _failure("refused", "the capability path is outside the workspace", code="PATH_DENIED")

    if previous is not None and previous.get("sourceDigest") != digest_text(source):
        return _failure(
            "refused",
            f"{capability_id} {version} already exists with different source; build a new version",
            code="VERSION_EXISTS",
        )

    try:
        _write_text(directory / "manifest.json", manifest.to_json())
        _write_text(directory / "capability.py", source)
        _write_text(directory / "test_capability.py", request.test or "")
        _write_text(directory / "README.md", _readme(manifest, request))
    except OSError as exc:
        return _failure(
            "refused",
            f"the capability draft could not be written: {exc}",
            code="DRAFT_WRITE_FAILED",
        )

    report = verify(
        manifest,
        source,
        request.test or "",
        dict(request.sample_inputs),
        timeout_s=max(1, min(request.timeout_ms // 1000, 600)),
    )

    if report.status == "unverified":
        status = "unverified"
    elif report.status == "verified":
        status = "tested"
    else:
        status = "unverified"

    activation = "none"
    if status == "tested" and manifest.scope == "workspace":
        active = store.records(capability_id=capability_id, status="active", limit=100)
        for record in active:
            if record.get("version") != version:
                store.set_status(capability_id, str(record.get("version")), "disabled")
        status = "active"
        activation = "auto"
    elif status == "tested":
        status = "approval_required"
        activation = "operator"

    record = _record(manifest, report, directory, status, run_id, request.resume_task_id)
    saved = store.save_record(record)
    if status == "active":
        register(manifest, source)
    store.set_request_status(request.request_id, "built" if status in ("active", "tested") else status)

    return {
        "status": status,
        "capabilityId": capability_id,
        "version": version,
        "activated": status == "active",
        "activation": activation,
        "requiresApproval": status == "approval_required",
        "dir": str(directory),
        "manifest": manifest.to_dict(),
        "verification": report.to_dict(),
        "record": saved,
        "reason": "" if report.ok else "the contract test did not pass",
    }


def activate(
    capability_id: str,
    version: Optional[str],
    *,
    store: CapabilityStore,
    operator: bool = False,
    root: Optional[Path] = None,
) -> dict[str, Any]:
    record = store.get(capability_id, version) if version else store.get(capability_id)
    if record is None:
        return _failure("not_found", "there is no such capability")
    manifest = CapabilityManifest.from_dict(record.get("manifest") or {})
    if manifest.effect != "read" or manifest.kind not in PURE_KINDS or manifest.scope == "global":
        if not operator:
            return _failure(
                "approval_required",
                "effectful and global capabilities are activated by an operator, not the agent",
                capabilityId=capability_id,
                version=record.get("version"),
            )
    if str(record.get("status")) not in ("tested", "approval_required", "disabled", "active"):
        return _failure(
            "unverified",
            "the capability has no passing contract test and cannot activate",
            capabilityId=capability_id,
            version=record.get("version"),
        )
    for other in store.records(capability_id=capability_id, status="active", limit=100):
        if other.get("version") != record.get("version"):
            store.set_status(capability_id, str(other.get("version")), "disabled")
    saved = store.set_status(capability_id, str(record.get("version")), "active")
    refresh_generated_recipes(store, Path(root) if root is not None else _default_root())
    return {
        "status": "active",
        "capabilityId": capability_id,
        "version": record.get("version"),
        "record": saved,
    }


def rollback(
    capability_id: str,
    version: Optional[str],
    *,
    store: CapabilityStore,
    root: Optional[Path] = None,
    operator: bool = False,
) -> dict[str, Any]:
    records = store.versions(capability_id)
    if not records:
        return _failure("not_found", "there are no versions of that capability")
    active = next((item for item in records if item.get("status") == "active"), None)
    target = None
    if version:
        target = next((item for item in records if item.get("version") == version), None)
    elif active is not None:
        active_index = records.index(active)
        for item in reversed(records[:active_index]):
            if item.get("status") in ("tested", "disabled", "active", "approval_required"):
                target = item
                break
    else:
        for item in reversed(records):
            if item.get("status") in ("tested", "disabled", "active", "approval_required"):
                target = item
                break
    if target is None:
        return _failure("not_found", "there is no previous version available for rollback")
    result = activate(
        capability_id, str(target.get("version")), store=store, operator=operator, root=root,
    )
    if result.get("status") == "active":
        result["rolledBackFrom"] = active.get("version") if active else None
    return result


def deactivate(
    capability_id: str,
    version: Optional[str],
    *,
    store: CapabilityStore,
    root: Optional[Path] = None,
) -> dict[str, Any]:
    record = store.get(capability_id, version) if version else store.get(capability_id)
    if record is None:
        return _failure("not_found", "there is no such capability")
    if str(record.get("status")) != "active":
        return _failure(
            "not_active",
            "that capability is not active",
            capabilityId=capability_id,
            version=record.get("version"),
        )
    saved = store.set_status(capability_id, str(record.get("version")), "disabled")
    remove_generated_recipe(capability_id)
    refresh_generated_recipes(store, Path(root) if root is not None else _default_root())
    return {
        "status": "disabled",
        "capabilityId": capability_id,
        "version": record.get("version"),
        "record": saved,
    }


def retire(
    capability_id: str,
    *,
    store: CapabilityStore,
) -> dict[str, Any]:
    current = store.get(capability_id)
    if current is None:
        return _failure("not_found", "there is no such capability")
    saved = store.set_status(capability_id, str(current.get("version")), "retired")
    remove_generated_recipe(capability_id)
    return {
        "status": "retired",
        "capabilityId": capability_id,
        "version": current.get("version"),
        "record": saved,
        "note": "files are kept for audit and rollback",
    }


def promote(
    capability_id: str,
    version: Optional[str],
    *,
    store: CapabilityStore,
    root: Optional[Path] = None,
    operator: bool = False,
) -> dict[str, Any]:
    """Copy a verified workspace recipe into the package's global capability root.

    Operator-only: a global capability ships with Eclipse, so the agent never
    promotes. The workspace files stay untouched; the record's scope/dir move to
    the global copy, which is what activation and the registry read afterwards.
    """
    if not operator:
        return _failure(
            "approval_required",
            "promoting a capability to global is an operator action",
            capabilityId=capability_id,
        )
    record = store.get(capability_id, version) if version else store.get(capability_id)
    if record is None:
        return _failure("not_found", "there is no such capability")
    try:
        manifest = CapabilityManifest.from_dict(record.get("manifest") or {})
    except Exception as exc:  # noqa: BLE001 - an unreadable manifest is a refusal
        return _failure("refused", f"the capability manifest is invalid: {exc}", code="MANIFEST_INVALID")
    if manifest.effect != "read" or manifest.kind not in PURE_KINDS:
        return _failure(
            "refused",
            "only read-only recipes can be promoted to global",
            code="EFFECTFUL",
            capabilityId=capability_id,
            version=record.get("version"),
        )
    if str(record.get("testStatus")) != "verified":
        return _failure(
            "unverified",
            "the capability has no passing contract test and cannot be promoted",
            capabilityId=capability_id,
            version=record.get("version"),
        )
    global_dir = global_root()
    source = Path(str(record.get("dir") or ""))
    base = Path(root) if root is not None else _default_root()
    if source.is_dir() and _path_inside(source, global_dir):
        return {
            "status": "global",
            "capabilityId": capability_id,
            "version": record.get("version"),
            "dir": str(source),
            "scope": "global",
            "idempotent": True,
            "record": record,
        }
    if base is None or not (source.is_dir() and _path_inside(source, draft_root(base))):
        return _failure(
            "refused",
            "the capability files are not in the workspace and cannot be promoted",
            code="PATH_DENIED",
            capabilityId=capability_id,
        )
    source_file = source / "capability.py"
    try:
        source_text = source_file.read_text(encoding="utf-8")
    except OSError as exc:
        return _failure("refused", f"the capability source is unreadable: {exc}", code="SOURCE_UNREADABLE")
    if record.get("sourceDigest") and record["sourceDigest"] != digest_text(source_text):
        return _failure(
            "refused",
            "the capability source changed after verification; rebuild it first",
            code="SOURCE_CHANGED",
            capabilityId=capability_id,
            version=record.get("version"),
        )
    destination = global_dir / _safe_component(capability_id) / _safe_component(str(record.get("version")))
    if not _path_inside(destination, global_dir):
        return _failure("refused", "the global capability path is invalid", code="PATH_DENIED")
    existing_source = destination / "capability.py"
    if existing_source.is_file():
        try:
            existing_text = existing_source.read_text(encoding="utf-8")
        except OSError:
            existing_text = ""
        if existing_text and digest_text(existing_text) != record.get("sourceDigest"):
            return _failure(
                "refused",
                "a different global version already exists at that path",
                code="GLOBAL_EXISTS",
                capabilityId=capability_id,
                version=record.get("version"),
            )
    data = manifest.to_dict()
    data["scope"] = "global"
    global_manifest = CapabilityManifest.from_dict(data)
    try:
        _write_text(destination / "manifest.json", global_manifest.to_json())
        _write_text(destination / "capability.py", source_text)
        for name in ("test_capability.py", "README.md"):
            file = source / name
            if file.is_file():
                _write_text(destination / name, file.read_text(encoding="utf-8"))
    except OSError as exc:
        return _failure(
            "refused",
            f"the global capability copy could not be written: {exc}",
            code="GLOBAL_WRITE_FAILED",
        )
    saved = store.save_record(CapabilityRecord(
        capability_id=capability_id,
        version=str(record.get("version")),
        kind=str(record.get("kind") or manifest.kind),
        title=str(record.get("title") or manifest.title),
        description=str(record.get("description") or manifest.description),
        scope="global",
        status=str(record.get("status")),
        manifest=global_manifest.to_dict(),
        source_digest=str(record.get("sourceDigest") or ""),
        test_digest=str(record.get("testDigest") or ""),
        test_status=str(record.get("testStatus") or ""),
        tests=list(record.get("tests") or []),
        directory=str(destination),
        run_id=record.get("runId"),
        task_id=record.get("taskId"),
        created_at=str(record.get("createdAt") or ""),
        updated_at=str(record.get("updatedAt") or ""),
    ))
    refresh_generated_recipes(store, base)
    return {
        "status": "global",
        "capabilityId": capability_id,
        "version": record.get("version"),
        "dir": str(destination),
        "scope": "global",
        "record": saved,
        "note": "the workspace copy is kept; activation now reads the global copy",
    }


__all__ = ["activate", "build", "deactivate", "promote", "retire", "rollback"]
