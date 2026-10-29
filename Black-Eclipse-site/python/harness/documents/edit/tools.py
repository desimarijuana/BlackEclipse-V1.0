"""`document_edit` — targeted, preservation-verified edits to Office/PDF files.

The tool never edits a user's original in place. It reads the source (an
artifactId or a confined path), applies a validated plan, verifies every
untouched package part, and publishes the result as a NEW artifact version (or
a new artifact when the source was a path). A failed verification publishes
nothing.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Any, Optional

from ...artifacts.model import ArtifactSourceType, AddVersionInput
from ...tools import ToolContext, ToolDefinition, ToolRegistry
from ..authoring import FORMAT_MIME
from .apply import apply_edit_plan, detect_format
from .plan import EditError, EditPlan

MAX_EDIT_BYTES = 256 * 1024 * 1024

_MIME = {
    "docx": FORMAT_MIME["docx"],
    "xlsx": FORMAT_MIME["xlsx"],
    "pptx": FORMAT_MIME["pptx"],
    "pdf": "application/pdf",
}


def _service(ctx: ToolContext) -> Any:
    service = getattr(ctx, "artifact_service", None)
    if service is None:
        from ...artifacts.bootstrap import get_artifact_service  # noqa: PLC0415

        service = get_artifact_service()
    if service is None:
        raise EditError("ARTIFACT_UNAVAILABLE", "the artifact service is not available")
    return service


def _owner(ctx: ToolContext) -> str:
    return str(getattr(ctx, "workspace_id", None) or "local")


def _allowed_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        from ...code.workspace import default_root  # noqa: PLC0415

        root = default_root()
        if root is not None:
            roots.append(Path(root))
    except Exception:  # noqa: BLE001
        pass
    try:
        from ...code.roots import TrustedRootStore  # noqa: PLC0415

        for entry in TrustedRootStore().list_roots():
            value = entry.get("path") if isinstance(entry, dict) else None
            if value:
                roots.append(Path(value))
    except Exception:  # noqa: BLE001
        pass
    try:
        from ...artifacts.storage import default_artifact_root  # noqa: PLC0415

        roots.append(default_artifact_root())
    except Exception:  # noqa: BLE001
        pass
    roots.append(Path(_session_root()))
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            resolved = root.expanduser().resolve()
        except OSError:
            continue
        key = str(resolved).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def _read_path(path: str) -> tuple[bytes, str]:
    roots = _allowed_roots()
    if not roots:
        raise EditError("EDIT_SOURCE_DENIED", "no authorized workspace is configured for file edits")
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = roots[0] / candidate
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise EditError("EDIT_SOURCE_INVALID", f"{path!r} could not be resolved") from exc
    allowed = False
    for root in roots:
        try:
            resolved.relative_to(root)
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        raise EditError(
            "EDIT_SOURCE_DENIED",
            "the source is outside every authorized workspace, trusted root, session folder and artifact store",
        )
    if not resolved.is_file():
        raise EditError("EDIT_SOURCE_NOT_FOUND", f"no file exists at {path!r}")
    size = resolved.stat().st_size
    if size > MAX_EDIT_BYTES:
        raise EditError("EDIT_LIMIT", "the source exceeds the edit size limit")
    with open(resolved, "rb") as handle:
        return handle.read(), resolved.name


def _session_root() -> str:
    override = os.environ.get("BLACK_ECLIPSE_SESSION_ROOT")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    site_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    return os.path.join(site_root, ".black-eclipse", "sessions")


def _read_session(ctx: ToolContext, name: str, kind: str) -> tuple[bytes, str]:
    chat_id = str(getattr(ctx, "session_id", None) or "").strip()
    if not chat_id:
        raise EditError("EDIT_SESSION_UNAVAILABLE", "this run has no conversation workspace")
    for part in (chat_id, name):
        if not part or part in (".", "..") or "/" in part or "\\" in part:
            raise EditError("EDIT_SESSION_INVALID", "invalid conversation/file name")
    folder = "output" if str(kind).casefold() == "output" else "context"
    root = os.path.realpath(_session_root())
    candidate = os.path.realpath(os.path.join(root, chat_id, folder, name))
    if not candidate.startswith(root + os.sep):
        raise EditError("EDIT_SESSION_INVALID", "the conversation file escapes the session root")
    if not os.path.isfile(candidate):
        raise EditError("EDIT_SOURCE_NOT_FOUND", f"the conversation has no {folder} file named {name!r}")
    size = os.path.getsize(candidate)
    if size > MAX_EDIT_BYTES:
        raise EditError("EDIT_LIMIT", "the source exceeds the edit size limit")
    with open(candidate, "rb") as handle:
        return handle.read(), os.path.basename(candidate)


def _read_artifact(ctx: ToolContext, artifact_id: str) -> tuple[bytes, str, Any]:
    service = _service(ctx)
    artifact = service.get(artifact_id, owner_id=_owner(ctx))
    handle, artifact = service.open_content(artifact_id, owner_id=_owner(ctx))
    try:
        data = handle.read()
    finally:
        try:
            handle.close()
        except Exception:  # noqa: BLE001
            pass
    if len(data) > MAX_EDIT_BYTES:
        raise EditError("EDIT_LIMIT", "the artifact exceeds the edit size limit")
    return data, artifact.name, artifact


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, EditError):
        return f"{exc.code}: {exc.message}", {"error": exc.code, "message": exc.message, "detail": exc.detail}
    return f"EDIT_ERROR: {exc}", {"error": "EDIT_ERROR", "message": str(exc)}


async def _edit(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    artifact_id = str(args.get("artifactId") or "").strip()
    path = str(args.get("source") or args.get("path") or "").strip()
    session_file = str(args.get("sessionFile") or "").strip()
    if not artifact_id and not path and not session_file:
        return _err(EditError(
            "EDIT_SOURCE_REQUIRED",
            "provide artifactId, sessionFile (a file attached to this conversation), or source/path",
        ))
    try:
        plan_payload = {
            "edits": args.get("edits"),
            "expectedSha256": args.get("expectedSha256"),
            "format": args.get("format"),
            "dryRun": bool(args.get("dryRun", False)),
            "deterministic": bool(args.get("deterministic", True)),
        }
        plan = EditPlan.from_dict(plan_payload)
        if artifact_id:
            data, name, artifact = _read_artifact(ctx, artifact_id)
        elif session_file:
            data, name = _read_session(ctx, session_file, str(args.get("sessionKind") or "context"))
            artifact = None
        else:
            data, name = _read_path(path)
            artifact = None
        outcome = apply_edit_plan(data, name, plan)
        try:
            ctx.log("document.edit", {
                "name": name,
                "format": outcome.format,
                "planHash": outcome.plan_hash,
                "sourceSha256": outcome.source_sha256,
                "targetedParts": outcome.report.get("targetedParts", []),
                "dryRun": plan.dry_run,
            })
        except Exception:  # noqa: BLE001 - telemetry must not break the edit
            pass
    except EditError as exc:
        return _err(exc)
    except Exception as exc:  # noqa: BLE001 - a bad plan must not crash the run
        return _err(exc)

    if plan.dry_run:
        report = outcome.report
        return (
            f"DRY RUN: {len(plan.edits)} edit(s) on {name}. Package parts: "
            f"{report.get('sourceParts', 0)} total, {len(report.get('targetedParts', []))} targeted, "
            f"{report.get('changedPartsCount', 0)} changed, "
            f"{report.get('unchangedParts', 0)} untouched preserved. No artifact was written.",
            {"status": "DRY_RUN", "name": name, "report": report, "bytes": len(outcome.data)},
        )

    mime = _MIME.get(outcome.format, "application/octet-stream")
    change_note = str(args.get("changeNote") or f"{len(plan.edits)} targeted edit(s)")[:1_000]
    try:
        service = _service(ctx)
        if artifact is not None:
            updated = service.add_version(
                artifact.id,
                AddVersionInput(
                    content_base64=base64.b64encode(outcome.data).decode("ascii"),
                    change_note=change_note,
                    mime_type=mime,
                    agent_id=str(getattr(ctx, "agent_id", None) or "eclipse-agent"),
                    run_id=getattr(ctx, "run_id", None),
                    idempotency_key=f"edit:{artifact.id}:{outcome.plan_hash}:{outcome.source_sha256}",
                    expected_checksum=outcome.source_sha256,
                ),
                owner_id=_owner(ctx),
                actor=str(getattr(ctx, "agent_id", None) or "eclipse-agent"),
            )
            verb = "versioned"
        else:
            updated = service.register_bytes(
                outcome.data,
                name=str(args.get("filename") or name),
                owner_id=_owner(ctx),
                description=change_note,
                mime_type=mime,
                source_type=ArtifactSourceType.TOOL,
                source_tool="document_edit",
                agent_id=str(getattr(ctx, "agent_id", None) or "eclipse-agent"),
                conversation_id=getattr(ctx, "conversation_id", None),
                run_id=getattr(ctx, "run_id", None),
                tags=list(args.get("tags") or []),
                idempotency_key=f"edit:{outcome.source_sha256}:{outcome.plan_hash}",
            )
            verb = "created"
    except Exception as exc:  # noqa: BLE001
        return _err(exc)

    report = outcome.report
    return (
        f"Edited {name}: {verb} artifact {updated.id} "
        f"(v{updated.version_number}) with {len(plan.edits)} targeted edit(s). "
        f"Package parts: {report.get('sourceParts', 0)} total, "
        f"{len(report.get('targetedParts', []))} targeted, "
        f"{report.get('changedPartsCount', 0)} changed, "
        f"{report.get('unchangedParts', 0)} untouched preserved.",
        {
            "status": "OK",
            "artifact": updated.model_dump(by_alias=True),
            "report": outcome.report,
            "format": outcome.format,
            "bytes": len(outcome.data),
        },
    )


def register_document_edit_tools(registry: ToolRegistry) -> list[str]:
    if registry.get("document_edit") is not None:
        return []
    registry.register(ToolDefinition(
        name="document_edit",
        description=(
            "Edit an existing Word, Excel, PowerPoint or PDF file without rebuilding it. "
            "Supply an artifactId (preferred), the name of a file attached to this conversation "
            "(`sessionFile`), or a source path, plus a small `edits` array. "
            "Supported operations: docx.replace_text, docx.set_paragraph_text, "
            "docx.set_table_cell, docx.set_core_property, docx.insert_image, "
            "docx.accept_revisions, docx.reject_revisions; xlsx.set_cell, xlsx.set_formula, "
            "xlsx.set_number_format, xlsx.rename_sheet, xlsx.append_rows, xlsx.insert_rows, "
            "xlsx.delete_rows, xlsx.insert_columns, xlsx.delete_columns; "
            "pptx.set_slide_title, pptx.replace_text, pptx.set_notes, pptx.set_shape_text, "
            "pptx.delete_slide, pptx.duplicate_slide, pptx.replace_chart_data, "
            "pptx.add_smartart_node, pptx.remove_smartart_node, pptx.set_smartart_node_text, "
            "pptx.set_smartart_layout; "
            "pdf.fill_form, pdf.rotate_pages, pdf.add_annotation, pdf.set_metadata, pdf.redact. "
            "The tool verifies that every untouched OOXML package part is byte-identical, "
            "then publishes a NEW artifact version. It never edits the original in place. "
            "Set dryRun=true to inspect the preservation report without writing."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "artifactId": {"type": "string", "description": "The artifact to edit (preferred)."},
                "sessionFile": {"type": "string", "description": "A file name attached to THIS conversation (the context folder), used when no artifactId exists yet."},
                "sessionKind": {"type": "string", "enum": ["context", "output"], "description": "Which conversation folder holds sessionFile (default context)."},
                "source": {"type": "string", "description": "A local path, used only when artifactId/sessionFile are absent."},
                "path": {"type": "string", "description": "Alias for source."},
                "format": {"type": "string", "enum": ["docx", "xlsx", "pptx", "pdf"]},
                "dryRun": {"type": "boolean", "description": "Apply in memory and return the report without publishing."},
                "deterministic": {"type": "boolean", "description": "Normalise ZIP timestamps for reproducible output (default true)."},
                "expectedSha256": {"type": "string", "description": "Refuse if the source changed since it was read."},
                "changeNote": {"type": "string"},
                "filename": {"type": "string", "description": "Name for a new artifact when editing a path."},
                "tags": {"type": "array", "items": {"type": "string"}},
                "edits": {
                    "type": "array",
                    "description": "Ordered, validated edit operations. One format per plan.",
                    "items": {"type": "object"},
                },
            },
            "required": ["edits"],
        },
        handler=_edit,
        permission="read",
        risk="low",
        timeout_ms=120_000,
    ))
    return ["document_edit"]


__all__ = ["register_document_edit_tools"]
