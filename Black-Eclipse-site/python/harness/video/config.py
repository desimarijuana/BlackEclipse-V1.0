"""Runtime configuration for the native video pipeline (fframes worker).

Every operational knob is env-overridable with safe desktop defaults; a bad
value falls back rather than crashing boot. The defaults describe THIS
repository's layout: the Rust worker binary under ``rust/fframes-worker/`` and
all runtime state under ``.black-eclipse/video/``.

Environment (all optional):

  HARNESS_VIDEO_ENABLED              1|0     (default 1)
  HARNESS_VIDEO_WORKER_BIN           path    fframes-worker executable
  HARNESS_VIDEO_FFMPEG_DIR           path    FFmpeg tree (falls back to FFMPEG_DIR)
  HARNESS_VIDEO_ROOT                 path    runtime root (jobs, projects)
  HARNESS_VIDEO_DRAFT_TIMEOUT_MS     int     (default 600000)
  HARNESS_VIDEO_FINAL_TIMEOUT_MS     int     (default 1800000)
  HARNESS_VIDEO_INSPECT_TIMEOUT_MS   int     (default 300000)
  HARNESS_VIDEO_PREVIEW_TIMEOUT_MS   int     (default 180000)
  HARNESS_VIDEO_TRANSIENT_RETRIES    int     (default 1; in-job retries for
                                              transient failures — a data
                                              fetch or worker spawn blip)
  HARNESS_VIDEO_MAX_CONCURRENT       int     (default 1)
  HARNESS_VIDEO_MAX_PENDING_PER_PROJECT int (default 4; queued+running jobs
                                              per project — a runaway loop is
                                              refused with TOO_MANY_PENDING)
  HARNESS_VIDEO_GC_ENABLED           1|0     (default 1; prune old job
                                              workspaces)
  HARNESS_VIDEO_GC_KEEP_JOBS         int     (default 20; newest kept)
  HARNESS_VIDEO_GC_MAX_TOTAL_MB      int     (default 2048; byte budget)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _int_env(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


@dataclass(frozen=True)
class VideoConfig:
    """Limits and paths for the video pipeline, shared by the service and the
    Fabric worker."""

    enabled: bool = True
    worker_bin: str = ""
    ffmpeg_dir: str = ""
    video_root: str = ""
    draft_timeout_ms: int = 600_000
    final_timeout_ms: int = 1_800_000
    inspect_timeout_ms: int = 300_000
    preview_timeout_ms: int = 180_000
    transient_retries: int = 1
    max_concurrent: int = 1
    # Resource limits (Phase 8): a per-project cap on queued+running jobs, and
    # the job-workspace budgets the boot sweep enforces.
    max_pending_per_project: int = 4
    gc_enabled: bool = True
    gc_keep_jobs: int = 20
    gc_max_total_mb: int = 2048
    timeout_slack_seconds: int = 60

    @classmethod
    def from_env(cls) -> "VideoConfig":
        return cls(
            enabled=_bool_env("HARNESS_VIDEO_ENABLED", True),
            worker_bin=(os.environ.get("HARNESS_VIDEO_WORKER_BIN") or "").strip(),
            ffmpeg_dir=(
                os.environ.get("HARNESS_VIDEO_FFMPEG_DIR")
                or os.environ.get("FFMPEG_DIR")
                or ""
            ).strip(),
            video_root=(os.environ.get("HARNESS_VIDEO_ROOT") or "").strip(),
            draft_timeout_ms=_int_env("HARNESS_VIDEO_DRAFT_TIMEOUT_MS", 600_000, minimum=1000),
            final_timeout_ms=_int_env("HARNESS_VIDEO_FINAL_TIMEOUT_MS", 1_800_000, minimum=1000),
            inspect_timeout_ms=_int_env("HARNESS_VIDEO_INSPECT_TIMEOUT_MS", 300_000, minimum=1000),
            preview_timeout_ms=_int_env("HARNESS_VIDEO_PREVIEW_TIMEOUT_MS", 180_000, minimum=1000),
            transient_retries=_int_env("HARNESS_VIDEO_TRANSIENT_RETRIES", 1, minimum=0),
            max_concurrent=_int_env("HARNESS_VIDEO_MAX_CONCURRENT", 1, minimum=1),
            max_pending_per_project=_int_env(
                "HARNESS_VIDEO_MAX_PENDING_PER_PROJECT", 4, minimum=1
            ),
            gc_enabled=_bool_env("HARNESS_VIDEO_GC_ENABLED", True),
            gc_keep_jobs=_int_env("HARNESS_VIDEO_GC_KEEP_JOBS", 20, minimum=1),
            gc_max_total_mb=_int_env("HARNESS_VIDEO_GC_MAX_TOTAL_MB", 2048, minimum=1),
        )

    @property
    def worker_timeout_ms(self) -> int:
        return self.final_timeout_ms + self.timeout_slack_seconds * 1000

    def resolve_worker_bin(self) -> Path:
        if self.worker_bin:
            return Path(self.worker_bin)
        from ..persistence import _harness_root  # noqa: PLC0415

        name = "fframes-worker.exe" if os.name == "nt" else "fframes-worker"
        return Path(_harness_root()) / "rust" / "fframes-worker" / "target" / "release" / name

    def resolve_video_root(self) -> Path:
        if self.video_root:
            return Path(self.video_root)
        from ..persistence import _harness_root  # noqa: PLC0415

        return Path(_harness_root()) / ".black-eclipse" / "video"

    def resolve_ffmpeg_dir(self) -> Optional[Path]:
        return Path(self.ffmpeg_dir) if self.ffmpeg_dir else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "workerBin": str(self.resolve_worker_bin()),
            "ffmpegDir": str(self.resolve_ffmpeg_dir()) if self.resolve_ffmpeg_dir() else None,
            "videoRoot": str(self.resolve_video_root()),
            "draftTimeoutMs": self.draft_timeout_ms,
            "finalTimeoutMs": self.final_timeout_ms,
            "inspectTimeoutMs": self.inspect_timeout_ms,
            "previewTimeoutMs": self.preview_timeout_ms,
            "transientRetries": self.transient_retries,
            "maxConcurrent": self.max_concurrent,
            "maxPendingPerProject": self.max_pending_per_project,
            "gcKeepJobs": self.gc_keep_jobs,
            "gcMaxTotalMb": self.gc_max_total_mb,
        }


_default: Optional[VideoConfig] = None


def get_video_config() -> VideoConfig:
    global _default
    if _default is None:
        _default = VideoConfig.from_env()
    return _default


__all__ = ["VideoConfig", "get_video_config"]
