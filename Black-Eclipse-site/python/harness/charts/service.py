"""The chart SERVICE — spec in, artifact out.

The service is the seam every chart surface uses:

    ChartSpec  →  render_chart()  →  PNG bytes  →  Artifact Center

The picture is always recorded in the Artifact Center, so a chart is
*discoverable* rather than merely displayed: it can be downloaded, versioned
and re-shared, exactly like a document the agent produced.

The honesty rules ride along with the picture:

* the figure is labelled ``computed`` — a picture is never evidence
  (ADR-H123);
* the spec's digest is recorded, so the SAME spec always yields the SAME
  picture and a different spec never reuses an old one;
* a rendering failure is a named refusal, never a blank image.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional

from .render import ChartRenderError, render_chart
from .spec import ChartSpec


@dataclass(frozen=True)
class RenderedChart:
    """A drawn chart and its identity."""

    spec: ChartSpec
    png: bytes
    sha256: str
    name: str

    @property
    def bytes(self) -> int:
        return len(self.png)

    def to_dict(self) -> dict[str, Any]:
        """The figure metadata that rides the wire.

        `isEvidence` is always False: a picture is the easiest way to break
        the retrieved-vs-computed rule, so the label is part of the contract.
        """
        return {
            "kind": self.spec.kind,
            "label": "computed",
            "isEvidence": False,
            "artifact": self.name,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "width": self.spec.width,
            "height": self.spec.height,
            "theme": self.spec.theme,
            "title": self.spec.title,
            "series": [
                {"name": s.name, "points": len(s.data)} for s in self.spec.series
            ],
            "summary": self.spec.summary(),
        }


def spec_digest(spec: ChartSpec) -> str:
    """The identity of a chart: the same spec always draws the same picture."""
    canonical = spec.model_dump_json(exclude_none=True, by_alias=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_spec(spec: ChartSpec) -> RenderedChart:
    """Draw the spec. Raises `ChartRenderError` when it cannot be drawn."""
    png = render_chart(spec)
    digest = hashlib.sha256(png).hexdigest()
    name = f"chart-{spec.kind}-{digest[:12]}.png"
    return RenderedChart(spec=spec, png=png, sha256=digest, name=name)


def register_chart_artifact(
    ctx: Any, rendered: RenderedChart, *, source_tool: str = "python_chart",
) -> Optional[Any]:
    """Record the drawn chart in the Artifact Center. Best-effort, never fatal.

    Returns the artifact entry, or None when the Artifact Center is not
    available — the chart itself is still rendered and still shown.
    """
    try:
        from ..artifacts.bootstrap import get_artifact_service  # noqa: PLC0415
        from ..artifacts.model import ArtifactCategory  # noqa: PLC0415

        service = getattr(ctx, "artifact_service", None) if ctx is not None else None
        service = service or get_artifact_service()
        if service is None:
            return None
        run_id = getattr(ctx, "run_id", None) if ctx is not None else None
        return service.register_bytes(
            rendered.png,
            name=rendered.name,
            owner_id="local",
            description=rendered.spec.summary(),
            category=ArtifactCategory.CHART,
            mime_type="image/png",
            source_tool=source_tool,
            run_id=run_id,
            tags=["chart", "computed"],
            idempotency_key=f"chart:{run_id or 'none'}:{rendered.sha256}",
            metadata=rendered.to_dict(),
        )
    except Exception:  # noqa: BLE001 - registration must never fail the chart
        return None


__all__ = [
    "RenderedChart",
    "register_chart_artifact",
    "render_spec",
    "spec_digest",
]
