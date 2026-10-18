"""Run-level collection of queued video jobs for the chat surface (Phase 7).

A `video_*` tool hands the job it just queued here — the same idiom as the
vision/document/image collectors — so an ordinary chat run carries ONE bounded
`video` blob listing what was queued. The chat renders it as a live job card:
progress while running, an inline player + download when a final succeeds,
cancel/regenerate controls, and a revise prompt. The blob is DETERMINISTIC:
every record comes from a real submitted job handle, and only successfully
queued work is collected. A failure to submit never reaches the collector —
the tool reports it to the model instead.
"""

from __future__ import annotations

from typing import Any, Optional

SCHEMA_VERSION = 1
MAX_RECORDS = 8
KINDS: tuple[str, ...] = ("preview", "render", "repair", "inspect")
_MODES: tuple[str, ...] = ("draft", "final")


class VideoJobCollector:
    """Bounded, de-duplicated per-run list of queued video jobs."""

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def add(self, record: Any) -> None:
        """Collect one queued-job record; malformed input is dropped, never fatal."""
        try:
            clean = self._clean(record)
            if clean is None:
                return
            for index, existing in enumerate(self._records):
                # The same job re-reported (e.g. a repair re-queued) keeps ONE
                # entry: the latest handle wins.
                if existing["jobId"] == clean["jobId"]:
                    self._records[index] = clean
                    return
            if len(self._records) >= MAX_RECORDS:
                self._records.pop(0)
            self._records.append(clean)
        except Exception:  # noqa: BLE001 - collection must never break a tool call
            return

    def to_blob(self) -> Optional[dict[str, Any]]:
        """The run blob for `update_run(video=...)`; None when nothing was queued."""
        if not self._records:
            return None
        return {
            "type": "video",
            "schemaVersion": SCHEMA_VERSION,
            "status": "collected",
            "count": len(self._records),
            "jobs": [dict(record) for record in self._records],
        }

    # ── internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _clean(record: Any) -> Optional[dict[str, Any]]:
        if not isinstance(record, dict):
            return None
        job_id = str(record.get("jobId") or "").strip()
        project_id = str(record.get("projectId") or "").strip()
        kind = str(record.get("kind") or "").strip().lower()
        if not job_id or not project_id or kind not in KINDS:
            return None
        clean: dict[str, Any] = {
            "jobId": job_id,
            "projectId": project_id,
            "kind": kind,
            "projectName": str(record.get("projectName") or "")[:200] or None,
        }
        mode = str(record.get("mode") or "").strip().lower()
        if mode in _MODES:
            clean["mode"] = mode
        of_job_id = str(record.get("ofJobId") or "").strip()
        if of_job_id:
            clean["ofJobId"] = of_job_id
        return clean


__all__ = ["KINDS", "MAX_RECORDS", "SCHEMA_VERSION", "VideoJobCollector"]
