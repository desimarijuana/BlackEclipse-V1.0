"""Local memory export / import / backup / reset.

Black Eclipse is a single-user local app: the operator owns the database file and
must be able to read it, move it, back it up and reset it. This module implements
that with the same safety posture as the rest of the memory system:

  * EXPORT is a readable JSON document (schema-tagged, versioned) — content the
    operator already owns, never secrets (secrets are refused on write);
  * IMPORT validates every record and runs it through the SAME `write_memory`
    authorization pipeline as a normal write (privacy/type/source/scope rules and
    conflict handling apply), records imported provenance, and is idempotent
    (duplicate/identical imports are skipped);
  * BACKUP copies the SQLite file with a consistent WAL checkpoint, never
    overwriting an existing backup;
  * RESET requires an explicit flag, backs up first, and deletes ONLY memory
    domain tables — unrelated application data is never touched.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
from typing import Any, Optional

from .db import now_iso

EXPORT_SCHEMA = "black-eclipse-memory-export"
# v2 adds `bundles` (skill bundles) and `projectTrust` (project-local skill trust)
# so a backup/restore or migration does not lose composability or trust
# provenance. A v1 document still imports (the new sections are simply absent).
EXPORT_VERSION = 2

# Memory-domain tables that a reset may clear. Skills/learning are NOT memory and
# are deliberately excluded, so a reset never destroys the skill library.
_MEMORY_TABLES = (
    "MemoryRecord", "MemoryEvidence", "MemoryLink", "MemoryRetrievalEvent",
    "MemoryEvent", "MemorySuggestion", "MemoryRecurrence", "MistakeRecord",
    "CorrectionRecord",
)


def _content_checksum(document: dict[str, Any]) -> str:
    """A stable sha256 over the export's content sections (not the checksum
    field itself), so a tampered/corrupted document is detectable on import."""
    import hashlib  # noqa: PLC0415

    payload = {
        "memories": document.get("memories") or [],
        "bundles": document.get("bundles") or [],
        "projectTrust": document.get("projectTrust") or [],
        "suggestions": document.get("suggestions") or [],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def export_payload(store: Any, *, include_inactive: bool = True) -> dict[str, Any]:
    """A readable, versioned JSON export of the memory domain."""
    memories = store.list_memories(limit=100_000, include_inactive=include_inactive)
    exported: list[dict[str, Any]] = []
    for memory in memories:
        exported.append({
            "content": memory["content"], "memoryType": memory["memoryType"],
            "scope": memory["scope"], "scopeId": memory.get("scopeId"),
            "subject": memory.get("subject"), "source": memory.get("source"),
            "confidence": memory.get("confidence"), "importance": memory.get("importance"),
            "verification": memory.get("verification"), "status": memory.get("status"),
            "authority": memory.get("authority"), "createdAt": memory.get("createdAt"),
            "expiresAt": memory.get("expiresAt"), "supersededBy": memory.get("supersededBy"),
            "structuredData": memory.get("structuredData"),
        })
    suggestions = store.list_suggestions(status=None, limit=100_000)
    bundles = store.list_skill_bundles()
    project_trust = store.list_project_trust()
    document: dict[str, Any] = {
        "schema": EXPORT_SCHEMA,
        "version": EXPORT_VERSION,
        "exportedAt": now_iso(),
        "sourceDatabase": os.path.basename(store.path or ""),
        "counts": {
            "memories": len(exported), "suggestions": len(suggestions),
            "bundles": len(bundles), "projectTrust": len(project_trust),
        },
        "memories": exported,
        "bundles": [
            {
                "id": b["id"], "name": b.get("name"), "description": b.get("description"),
                "skills": b.get("skills"), "instruction": b.get("instruction"),
                "constraints": b.get("constraints"), "provenance": b.get("provenance"),
                "version": b.get("version"), "memberVersions": b.get("memberVersions"),
                "locked": b.get("locked"),
            }
            for b in bundles
        ],
        "projectTrust": [
            {"path": t["path"], "trusted": t.get("trusted"), "trustedAt": t.get("trustedAt"), "note": t.get("note")}
            for t in project_trust
        ],
        "suggestions": [
            {
                "content": s["content"], "memoryType": s["memoryType"], "scope": s["scope"],
                "scopeId": s.get("scopeId"), "subject": s.get("subject"),
                "reason": s.get("reason"), "status": s.get("status"),
                "createdAt": s.get("createdAt"),
            }
            for s in suggestions
        ],
    }
    document["checksum"] = _content_checksum(document)
    return document


def export_json(store: Any, *, include_inactive: bool = True) -> str:
    return json.dumps(export_payload(store, include_inactive=include_inactive), indent=2, ensure_ascii=False)


def _signature(memory_type: str, scope: str, scope_id: Optional[str], subject: Optional[str], content: str) -> str:
    from .service import _content_signature  # noqa: PLC0415

    return _content_signature(memory_type, scope, scope_id, subject, content)


def import_payload(
    service: Any,
    payload: dict[str, Any],
    *,
    source: str = "imported",
    dry_run: bool = False,
    scope_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    bundles_only: bool = False,
) -> dict[str, Any]:
    """Validate + import an export document through the normal write pipeline.

    Returns a report: `{imported, skipped, rejected: [{reason}], dryRun,
    checksumOk, validationErrors}`. Every accepted record is written by
    `EclipseMemoryService.write_memory` with `source='imported'`, so
    privacy/type/scope/conflict rules and duplicate detection all apply. Rejected
    records carry a reason; nothing is silently dropped and nothing unsafe is
    written.

    A `checksum` carried by the document is verified before any write; a mismatch
    raises (a tampered/corrupted file is never partially applied). `dry_run`
    validates and counts without writing. `scope_filter`/`type_filter`/
    `bundles_only` support a PARTIAL restore by category or scope.
    """
    if not isinstance(payload, dict):
        raise ValueError("import payload must be a JSON object")
    schema = payload.get("schema")
    if schema != EXPORT_SCHEMA:
        raise ValueError(f"unrecognized export schema {schema!r}")
    if int(payload.get("version", 0)) > EXPORT_VERSION:
        raise ValueError("export was produced by a newer version; update before importing")
    # Integrity: verify the content checksum BEFORE any write, so a corrupted or
    # tampered document is never partially applied.
    checksum_ok: Optional[bool] = None
    if payload.get("checksum"):
        expected = payload.get("checksum")
        actual = _content_checksum({k: v for k, v in payload.items() if k != "checksum"})
        checksum_ok = expected == actual
        if not checksum_ok:
            raise ValueError("import checksum mismatch — the document is corrupted or was modified")
    records = payload.get("memories")
    if not isinstance(records, list):
        raise ValueError("import payload is missing a 'memories' list")

    # Partial restore: filter records by scope/type before writing.
    if scope_filter:
        records = [r for r in records if isinstance(r, dict) and str(r.get("scope")) == scope_filter]
    if type_filter:
        records = [r for r in records if isinstance(r, dict) and str(r.get("memoryType")) == type_filter]
    if bundles_only:
        records = []

    seen: set[str] = set()
    imported = 0
    skipped = 0
    rejected: list[dict[str, Any]] = []
    imported_ids: list[str] = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            rejected.append({"index": index, "reason": "record is not an object"})
            continue
        content = str(record.get("content") or "").strip()
        if not content:
            rejected.append({"index": index, "reason": "empty content"})
            continue
        memory_type = str(record.get("memoryType") or "semantic")
        scope = str(record.get("scope") or "general")
        scope_id = record.get("scopeId")
        subject = record.get("subject")
        signature = _signature(memory_type, scope, scope_id, subject, content)
        # Duplicate within the file.
        if signature in seen:
            skipped += 1
            continue
        seen.add(signature)
        # Duplicate of an existing active memory: skip (idempotent re-import).
        if service._find_duplicate(signature):
            skipped += 1
            continue
        if dry_run:
            imported += 1
            continue
        try:
            # Run the SAME shared decision gate as any other write, so privacy
            # (secrets/credentials/dumps), financial-fact and content rules apply
            # to an imported record exactly as to a normal one.
            from .decision import authorize_proposal  # noqa: PLC0415

            decision = authorize_proposal(
                content=content, provenance="ui_save",
                user_id=scope_id, memory_type=memory_type, scope=scope,
                scope_id=scope_id, subject=subject,
                confidence=float(record.get("confidence") or 0.6),
                settings=service.policy.get_all(),
            )
            if decision.outcome != "save":
                rejected.append({"index": index, "reason": decision.reason or "rejected by policy"})
                continue
            # The import provenance is a permitted source (see service.VALID_SOURCES).
            memory = service.write_memory(
                memory_type=memory_type, content=content, source=source,
                scope=scope, scope_id=scope_id, subject=subject,
                confidence=float(record.get("confidence") or 0.6),
                importance=float(record.get("importance") or 0.5),
                verification=str(record.get("verification") or "unverified"),
                structured_data=record.get("structuredData"),
            )
            imported += 1
            imported_ids.append(memory["id"])
        except Exception as exc:  # noqa: BLE001 - a bad record is reported, not fatal
            rejected.append({"index": index, "reason": str(exc)})

    # Bundles and project trust are control-plane references, not memory content.
    # They are imported verbatim (they carry no secrets and are validated for
    # shape); project trust is imported as data only — a restored trust record
    # simply re-affirms a decision the operator already made on the source
    # machine. Neither path can enable a skill.
    imported_bundles = 0
    imported_trust = 0
    if not dry_run:
        for bundle in payload.get("bundles") or []:
            if not isinstance(bundle, dict) or not bundle.get("id"):
                continue
            try:
                from ..skills.bundles import BundleError, SkillBundle  # noqa: PLC0415

                parsed = SkillBundle(
                    id=str(bundle["id"]), name=str(bundle.get("name") or ""),
                    description=str(bundle.get("description") or ""),
                    skills=[str(s) for s in (bundle.get("skills") or [])],
                    instruction=str(bundle.get("instruction") or ""),
                    constraints=str(bundle.get("constraints") or ""),
                    provenance=str(bundle.get("provenance") or "imported"),
                    version=str(bundle.get("version") or "1.0.0"),
                    member_versions=dict(bundle.get("memberVersions") or {}),
                    locked=bool(bundle.get("locked")),
                )
                service.store.save_skill_bundle(parsed.to_dict())
                imported_bundles += 1
            except BundleError:
                continue
            except Exception:  # noqa: BLE001 - a bad bundle is skipped, never fatal
                continue
        for trust in payload.get("projectTrust") or []:
            if not isinstance(trust, dict) or not trust.get("path"):
                continue
            try:
                service.store.set_project_trust(
                    str(trust["path"]), bool(trust.get("trusted")), note=trust.get("note"),
                )
                imported_trust += 1
            except Exception:  # noqa: BLE001
                continue

    if not dry_run and (imported or imported_bundles or imported_trust):
        service.store.append_memory_event(
            "memory.imported", data={"imported": imported, "skipped": skipped,
                                     "rejected": len(rejected), "source": source,
                                     "bundles": imported_bundles, "projectTrust": imported_trust},
        )
    return {
        "imported": imported, "skipped": skipped, "rejected": rejected,
        "dryRun": dry_run, "importedIds": imported_ids,
        "importedBundles": imported_bundles, "importedProjectTrust": imported_trust,
        "checksumOk": checksum_ok,
        "filters": {"scope": scope_filter, "type": type_filter, "bundlesOnly": bundles_only},
        "importable": imported,  # for dry-run previews
    }


# ── Backup / health / reset ─────────────────────────────────────────────────


def create_backup(store: Any, backup_path: Optional[str] = None) -> dict[str, Any]:
    """A consistent copy of the SQLite database. Never overwrites an existing
    file (use a unique name), and checkpoints WAL first so the copy is complete."""
    source_path = store.path
    if not source_path or not os.path.isfile(source_path):
        raise FileNotFoundError("no memory database to back up")
    if backup_path is None:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        backup_path = f"{source_path}.backup-{stamp}"
    if os.path.exists(backup_path):
        raise FileExistsError(f"backup path already exists: {backup_path}")
    # Flush WAL into the main database so a plain file copy is consistent.
    try:
        store._db.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        store._db.commit()
    except Exception:  # noqa: BLE001 - a checkpoint failure is non-fatal for a copy
        pass
    # Copy to a temporary sibling then atomically rename, so an interrupted
    # backup can never leave a partial file at the destination path.
    temp_path = f"{backup_path}.partial"
    try:
        shutil.copy2(source_path, temp_path)
        os.replace(temp_path, backup_path)
    except Exception:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        raise
    return {"ok": True, "path": backup_path, "bytes": os.path.getsize(backup_path), "at": now_iso()}


def database_health(store: Any) -> dict[str, Any]:
    """A stronger health check than integrity_check alone: integrity, foreign-key
    violations, and free-page ratio (a proxy for bloat)."""
    report: dict[str, Any] = {"path": store.path, "ok": True}
    try:
        report["integrity"] = store._db.execute("PRAGMA integrity_check").fetchone()[0]
        report["foreignKeyViolations"] = len(
            store._db.execute("PRAGMA foreign_key_check").fetchall()
        )
        page_count = store._db.execute("PRAGMA page_count").fetchone()[0]
        free_pages = store._db.execute("PRAGMA freelist_count").fetchone()[0]
        report["pageCount"] = page_count
        report["freePages"] = free_pages
        report["freeRatio"] = round(free_pages / page_count, 4) if page_count else 0.0
        report["ok"] = report["integrity"] == "ok" and report["foreignKeyViolations"] == 0
    except Exception as exc:  # noqa: BLE001 - health must never raise
        report["ok"] = False
        report["error"] = str(exc)
    return report


def reset_memory(
    store: Any,
    *,
    confirm: bool = False,
    backup_first: bool = True,
) -> dict[str, Any]:
    """Delete the memory domain only. Requires an explicit `confirm=True`.

    A backup is taken first by default. Skill/learning tables and every
    unrelated application database are never touched.
    """
    if not confirm:
        raise PermissionError("reset requires explicit confirmation")
    backup: Optional[dict[str, Any]] = None
    if backup_first:
        try:
            backup = create_backup(store)
        except Exception as exc:  # noqa: BLE001 - a failed backup blocks the reset
            raise PermissionError(f"reset aborted: backup failed ({exc})") from exc

    existing = {
        row["name"]
        for row in store._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    cleared: dict[str, int] = {}
    try:
        for table in _MEMORY_TABLES:
            if table not in existing:
                continue
            count = store._db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            store._db.execute(f"DELETE FROM {table}")
            cleared[table] = int(count)
        store._db.commit()
        store._db.execute("VACUUM;")
    except Exception as exc:  # noqa: BLE001
        store._db.rollback()
        raise RuntimeError(f"reset failed: {exc}") from exc
    return {"ok": True, "cleared": cleared, "backup": backup}


__all__ = [
    "EXPORT_SCHEMA", "EXPORT_VERSION", "create_backup", "database_health",
    "export_json", "export_payload", "import_payload", "reset_memory",
]
