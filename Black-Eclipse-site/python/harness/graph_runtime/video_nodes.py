"""Video-production node declarations for Graph Studio (Phase 8).

The node type below names the integration surface for the native video
pipeline. It is DELIBERATELY executor-less for now, and says so (`since_phase`):
the graph runtime's executors are synchronous, while a render is an ASYNC queued
Execution-Fabric job that writes files and registers an Artifact Center entry;
and every UI/schedule-reachable run uses the test-run envelope that refuses
effectful nodes. Declaring the contract here makes the gap explicit in the
palette and in compile diagnostics (`executor_unavailable`) instead of shipping
a node that pretends to render.

The executor arrives when the graph runtime grows async node execution + an
operator-run envelope for effectful nodes (Graph Studio's own phase). The video
pipeline itself is already reachable from the agent tools, the `/video` HTTP
surface, and automation `call_tool` actions.
"""

from __future__ import annotations

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef

_ALL = tuple(ExecutionMode)


def build_video_nodes() -> list[NodeDef]:
    """The video node set (declarations only — see the module docstring)."""
    return [
        NodeDef(
            type="video.render",
            version="1.0.0",
            label="Video render",
            category="finance",
            inputs=(
                PortDef(id="symbols", name="Symbols", type=PortType.ARRAY),
            ),
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
            executor=None,
            since_phase=(
                "async graph execution + an operator-run envelope for effectful "
                "nodes (Graph Studio Phase 7+)"
            ),
            metadata={
                "docs": (
                    "Builds a data-bound market-recap storyboard and queues the render "
                    "through the native video pipeline. Until the executor exists, use "
                    "video_render_final / POST /video/projects/{id}/render."
                ),
            },
        ),
    ]


__all__ = ["build_video_nodes"]
