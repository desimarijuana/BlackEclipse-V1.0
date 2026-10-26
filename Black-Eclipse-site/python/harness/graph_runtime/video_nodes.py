"""Video-production node for Graph Studio.

The node builds a data-bound market-recap storyboard and runs the EXISTING
VideoService render pipeline in the graph worker thread. It is a local WRITE
(project files + Artifact Center entry), never a live action: the compiler only
allows it in an operator run that explicitly granted writes, and a test run
always refuses it.

It does not create a second renderer or a second queue. The video bootstrap owns
the service, Rust worker and market-data provider; this is the graph seam.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_SYMBOLS = 5

VideoRunner = Callable[[NodeExecContext, list[str], str, str], dict[str, Any]]
_runner: Optional[VideoRunner] = None


def set_video_runner(runner: Optional[VideoRunner]) -> None:
    global _runner
    _runner = runner


def exec_video_render(context: NodeExecContext) -> dict[str, Any]:
    raw = context.inputs.get("symbols")
    if not isinstance(raw, list) or not raw:
        raise ValueError("video.render needs a non-empty symbols array")
    if len(raw) > MAX_SYMBOLS:
        raise ValueError(f"video.render is bounded to {MAX_SYMBOLS} symbols")
    symbols: list[str] = []
    for index, item in enumerate(raw):
        value = str(item or "").strip().upper()
        if not value or len(value) > 16:
            raise ValueError(f"symbol {index + 1} is invalid")
        symbols.append(value)
    title = str(context.config.get("title") or "Market recap")[:80]
    mode = str(context.config.get("mode") or "draft")
    if mode not in ("draft", "final"):
        raise ValueError("mode must be draft or final")
    if _runner is None:
        raise ValueError("the video pipeline is not configured in this graph runtime")
    result = _runner(context, symbols, title, mode)
    if not isinstance(result, dict) or "project" not in result:
        raise ValueError("the video pipeline returned no project")
    context.emit(f"video {mode} render {result.get('job', {}).get('status', 'queued')}: {title}")
    return {"project": result.get("project"), "job": result.get("job")}


def build_video_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="video.render",
            version="1.0.0",
            label="Video render",
            category="finance",
            inputs=(PortDef(id="symbols", name="Symbols", type=PortType.ARRAY),),
            outputs=(
                PortDef(id="project", name="Project", type=PortType.OBJECT),
                PortDef(id="job", name="Job", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("title", "string", "Market recap", max_length=80),
                ConfigField("mode", "enum", "draft", enum=("draft", "final")),
            ),
            capabilities=("video.render",),
            side_effects=SideEffect.WRITE,
            allowed_modes=_ALL,
            timeout_ms=3_600_000,
            executor=exec_video_render,
            metadata={
                "docs": (
                    "Builds a bound market-recap storyboard and runs the existing "
                    "VideoService render pipeline. Local files + an artifact; requires "
                    "an operator run with an explicit write grant."
                ),
            },
        ),
    ]


__all__ = ["build_video_nodes", "exec_video_render", "set_video_runner"]
