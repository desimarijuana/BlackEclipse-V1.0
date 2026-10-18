"""Shared helpers for the video pipeline tests (offline, deterministic).

The fframes worker is replaced by a tiny Python script with the SAME machine
contract — one JSON document on stdout, JSON events on stderr, `-o <path>`,
exit codes. `FAKE_VIDEO_SCENARIO` / `FAKE_VIDEO_INSPECT` select the scenario so
the child process stays configurable per test. A fully wired fixture bundles a
`VideoService`, a real (temp) ArtifactService and a real ExecutionManager.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from fabric_helpers import make_manager
from harness.artifacts.service import ArtifactService
from harness.artifacts.storage import LocalArtifactStorage
from harness.artifacts.store import ArtifactStore
from harness.persistence import AgentMemoryStore
from harness.video.config import VideoConfig
from harness.video.fabric import build_video_worker
from harness.video.projects import VideoProjectStore
from harness.video.runner import VideoRunner
from harness.video.service import VideoService, set_video_service

FAKE_WORKER_SOURCE = '''
import json, os, sys, time

def _out_path(args):
    return args[args.index("-o") + 1]

def _emit(event):
    print(json.dumps(event), file=sys.stderr, flush=True)

scenario = os.environ.get("FAKE_VIDEO_SCENARIO", "success")
inspect_bad = os.environ.get("FAKE_VIDEO_INSPECT") == "bad"
args = sys.argv[1:]

if scenario == "sleep":
    _emit({"event": "start", "frames": 300})
    time.sleep(60)
    sys.exit(0)

if scenario == "fail":
    print("boom: invalid svg", file=sys.stderr, flush=True)
    sys.exit(3)

if scenario == "nooutput":
    print(json.dumps({"output": "does-not-exist.mp4", "frames": {"start": 0, "end": 10},
                      "width": 100, "height": 100, "elapsed_seconds": 0.1}))
    sys.exit(0)

if args and args[0] == "render":
    total = 50 if "--draft" in args else 300
    _emit({"event": "start", "frames": total})
    for done in range(10, total + 1, 10):
        _emit({"event": "progress", "done": done, "total": total, "elapsed": 0.05})
    path = _out_path(args)
    with open(path, "wb") as handle:
        handle.write(b"fake-mp4-bytes" * 64)
    print(json.dumps({"output": path, "frames": {"start": 0, "end": total},
                      "start_seconds": 0.0, "end_seconds": 10.0, "width": 1920,
                      "height": 1080, "elapsed_seconds": 0.2}))
    sys.exit(0)

if args and args[0] == "inspect":
    findings = [{"severity": "error", "message": "text is clipped at frame 12"}] if inspect_bad else []
    print(json.dumps({"checked_frames": 39, "findings": findings}))
    sys.exit(2 if findings else 0)

sys.exit(9)
'''


def write_fake_worker(tmp_path: Path) -> Path:
    script = tmp_path / "fake_fframes_worker.py"
    script.write_text(FAKE_WORKER_SOURCE, encoding="utf-8")
    return script


def make_video_env(tmp_path: Path, monkeypatch: Any, *, worker_bin: Optional[str] = None) -> dict[str, Any]:
    """A wired service + artifacts + manager. `worker_bin` overrides the binary
    path for environment-report tests (the child is then never spawned).

    `BLACK_ECLIPSE_CODE_ROOT` points at tmp_path so the tmp video workspace is
    an authorized artifact-import root (the operator/test override
    `code.workspace.default_root()` documents)."""
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    script = write_fake_worker(tmp_path)
    config = VideoConfig(
        video_root=str(tmp_path / "video"),
        worker_bin=worker_bin or str(script),
        draft_timeout_ms=15_000,
        final_timeout_ms=15_000,
        inspect_timeout_ms=15_000,
    )
    runner = VideoRunner(config)
    if worker_bin is None:
        monkeypatch.setattr(runner, "worker_argv", lambda: [sys.executable, str(script)])
    aml = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    artifacts = ArtifactService(
        ArtifactStore(aml), LocalArtifactStorage(root=tmp_path / "artifacts")
    )
    manager = make_manager(aml)
    manager.register_worker(build_video_worker(None))
    service = VideoService(
        config=config,
        runner=runner,
        projects=VideoProjectStore(config.resolve_video_root() / "projects"),
        artifact_provider=lambda: artifacts,
        manager_provider=lambda: manager,
    )
    set_video_service(service)
    return {
        "service": service, "artifacts": artifacts, "manager": manager,
        "script": script, "config": config, "aml": aml,
    }
