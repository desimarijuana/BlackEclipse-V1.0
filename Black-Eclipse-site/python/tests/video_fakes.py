"""Shared helpers for the video pipeline tests (offline, deterministic).

The fframes worker is replaced by a tiny Python script with the SAME machine
contract — one JSON document on stdout, JSON events on stderr, `--project`
before the subcommand, `-o <path>`, exit codes — and it records the argv it
received next to every rendered file (`<out>.argv.json`) so tests can assert
what the runner actually invoked. `FAKE_VIDEO_SCENARIO` / `FAKE_VIDEO_INSPECT`
select the scenario. A fully wired fixture bundles a `VideoService`, a real
(temp) ArtifactService and a real ExecutionManager.
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
import json, os, sys, tempfile, time

def _out_path(args):
    return args[args.index("-o") + 1]

def _emit(event):
    print(json.dumps(event), file=sys.stderr, flush=True)

def _png(path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(b"fake-png-bytes" * 32)

def _record_argv(path, args):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(args, handle)

scenario = os.environ.get("FAKE_VIDEO_SCENARIO", "success")
inspect_bad = os.environ.get("FAKE_VIDEO_INSPECT") == "bad"
preview_findings = os.environ.get("FAKE_VIDEO_PREVIEW") == "findings"
args = sys.argv[1:]
command = next((a for a in args if a in ("render", "inspect", "strip", "frame")), "")

if scenario == "flaky":
    counter_file = os.environ.get("FAKE_VIDEO_COUNTER_FILE")
    count = 0
    if counter_file:
        try:
            with open(counter_file, encoding="utf-8") as handle:
                count = int(handle.read() or "0")
        except Exception:
            count = 0
        with open(counter_file, "w", encoding="utf-8") as handle:
            handle.write(str(count + 1))
    if count < int(os.environ.get("FAKE_VIDEO_FAIL_TIMES", "1")):
        print("transient boom", file=sys.stderr, flush=True)
        sys.exit(2)

if scenario == "sleep":
    _emit({"event": "start", "frames": 300})
    time.sleep(60)
    sys.exit(0)

if scenario == "slow" and command == "render":
    time.sleep(0.4)

if scenario == "fail":
    print("boom: invalid svg", file=sys.stderr, flush=True)
    sys.exit(3)

if scenario == "nooutput":
    print(json.dumps({"output": "does-not-exist.mp4", "frames": {"start": 0, "end": 10},
                      "width": 100, "height": 100, "elapsed_seconds": 0.1}))
    sys.exit(0)

if command == "strip":
    out = _out_path(args)
    if scenario == "escape_strip":
        # A (buggy/hostile) worker reporting output outside the job workspace.
        out = os.path.join(tempfile.gettempdir(), "escaped-strip.png")
    _png(out)
    _record_argv(out + ".argv.json", args)
    reports = []
    if preview_findings:
        reports = [{
            "frame": 3, "seconds": 0.10, "scenes": ["Intro"],
            "diagnostics": [{
                "severity": "warning", "key": "text_clipped:TOO LONG TITLE",
                "message": "text \\"TOO LONG TITLE\\" is cut off by the canvas edge",
                "kind": "text_clipped", "text": "TOO LONG TITLE",
                "bbox": [100.0, 200.0, 1900.0, 120.0],
            }],
        }]
    print(json.dumps({"output": out, "frames": [0, 12, 25, 37, 50], "diagnostics": reports}))
    sys.exit(0)

if command == "frame":
    marker = args.index("frame")
    specs, index = [], marker + 1
    while index < len(args) and args[index] != "-o":
        if not args[index].startswith("-"):
            specs.append(args[index])
        index += 1
    out_dir = args[args.index("-o") + 1]
    os.makedirs(out_dir, exist_ok=True)
    _record_argv(os.path.join(out_dir, "argv.json"), args)
    results = []
    for spec in specs:
        name = "".join(c.lower() if c.isalnum() or c in ".-" else "_" for c in spec).strip("_")
        path = os.path.join(out_dir, (name or "frame") + ".png")
        _png(path)
        try:
            seconds = float(spec.rstrip("s"))
        except ValueError:
            seconds = 1.0
        results.append({"spec": spec, "path": path, "frame": 10,
                        "seconds": seconds, "scenes": ["Intro"], "diagnostics": []})
    print(json.dumps(results))
    sys.exit(0)

if command == "render":
    total = 50 if "--draft" in args else 300
    _emit({"event": "start", "frames": total})
    for done in range(10, total + 1, 10):
        _emit({"event": "progress", "done": done, "total": total, "elapsed": 0.05})
    path = _out_path(args)
    if scenario == "escape_render":
        path = os.path.join(tempfile.gettempdir(), "escaped-render.mp4")
    with open(path, "wb") as handle:
        handle.write(b"fake-mp4-bytes" * 64)
    _record_argv(path + ".argv.json", sys.argv[1:])
    print(json.dumps({"output": path, "frames": {"start": 0, "end": total},
                      "start_seconds": 0.0, "end_seconds": 10.0, "width": 1920,
                      "height": 1080, "elapsed_seconds": 0.2}))
    sys.exit(0)

if command == "inspect":
    findings = [{"severity": "error", "message": "text is clipped at frame 12"}] if inspect_bad else []
    print(json.dumps({"checked_frames": 39, "findings": findings}))
    sys.exit(2 if findings else 0)

sys.exit(9)
'''


def write_fake_worker(tmp_path: Path) -> Path:
    script = tmp_path / "fake_fframes_worker.py"
    script.write_text(FAKE_WORKER_SOURCE, encoding="utf-8")
    return script


def fake_meta(**overrides: Any) -> dict[str, Any]:
    """A market-record meta block shaped like the gateway's."""
    meta = {
        "provider": "yahoo", "source": "yahoo",
        "retrievedAt": "2026-10-18T03:12:44+00:00",
        "dataTimestamp": "2026-10-18T03:11:00+00:00",
        "freshness": "delayed", "stale": False, "quality": "valid",
        "warnings": [], "currency": "USD", "dataStatus": "OK",
    }
    meta.update(overrides)
    return meta


class FakeMarketProvider:
    """A `video.data` provider with configurable behaviour (offline, no network)."""

    def __init__(
        self, *, price: float = 68240.5, change: float = 2.41,
        volume: float = 3.82e10, bars: int = 14, stale: bool = False,
        missing_field: bool = False, fail: bool = False, short_bars: bool = False,
        fail_times: int = 0,
    ) -> None:
        self.price = price
        self.change = change
        self.volume = volume
        self.bars = bars
        self.stale = stale
        self.missing_field = missing_field
        self.fail = fail
        self.short_bars = short_bars
        self.fail_times = fail_times
        self.calls: list[tuple] = []

    def _maybe_transient_failure(self) -> None:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("provider down")

    async def quote(self, symbol: str, market: Any = None) -> dict[str, Any]:
        self.calls.append(("quote", symbol, market))
        self._maybe_transient_failure()
        if self.fail:
            raise RuntimeError("provider down")
        return {
            "price": None if self.missing_field else self.price,
            "changePct": self.change,
            "volume": self.volume,
            "currency": "USD",
            "meta": fake_meta(stale=self.stale, dataStatus="STALE" if self.stale else "OK"),
        }

    async def candles(self, symbol: str, market: Any, interval: str, count: int) -> dict[str, Any]:
        self.calls.append(("candles", symbol, interval, count))
        self._maybe_transient_failure()
        if self.fail:
            raise RuntimeError("provider down")
        total = 1 if self.short_bars else self.bars
        rows = [
            {
                "t": f"2026-10-{index + 1:02d}T00:00:00+00:00",
                "o": 64000.0 + index * 40.0,
                "h": 64120.0 + index * 40.0,
                "l": 63940.0 + index * 40.0,
                "c": 64080.0 + index * 40.0,
            }
            for index in range(total)
        ]
        return {
            "bars": rows,
            "meta": fake_meta(
                provider="yfinance", source="yfinance",
                freshness="daily", stale=self.stale,
                dataStatus="STALE" if self.stale else "OK",
            ),
        }


def make_video_env(
    tmp_path: Path, monkeypatch: Any, *, worker_bin: Optional[str] = None,
    data_provider: Any = None, transient_retries: int = 1,
) -> dict[str, Any]:
    """A wired service + artifacts + manager. `worker_bin` overrides the binary
    path for environment-report tests (the child is then never spawned);
    `data_provider` injects a fake market provider for binding tests.

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
        preview_timeout_ms=15_000,
        transient_retries=transient_retries,
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
        data_provider=(lambda: data_provider) if data_provider is not None else None,
    )
    set_video_service(service)
    return {
        "service": service, "artifacts": artifacts, "manager": manager,
        "script": script, "config": config, "aml": aml,
    }
