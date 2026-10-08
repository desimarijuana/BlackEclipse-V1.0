"""Image tiling for large images.

A large screenshot analyzed as one downscaled frame loses small text and
controls. Tiling splits a big image into overlapping tiles, analyzes each (in
parallel), then merges observations. Overlap regions are deduplicated by
IoU/centre-distance so the same element detected twice becomes one observation.

The tile grid is pure geometry (testable offline); only the analysis is I/O.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from .contracts import Region, VisualObservation
from .image import DecodedImage


@dataclass
class Tile:
    index: int
    row: int
    col: int
    region: Region  # in the ORIGINAL image's pixel coordinates

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "row": self.row, "col": self.col, "region": self.region.to_dict()}


def plan_tiles(
    width: int,
    height: int,
    *,
    tile_size: int,
    overlap: float = 0.1,
    max_tiles: int = 16,
) -> list[Tile]:
    """Compute an overlapping tile grid that covers the whole image.

    The tile count is capped at `max_tiles`; when the natural grid exceeds the
    cap the tile size is grown so coverage is preserved with fewer tiles (never
    silently leaving part of the image unanalyzed).
    """
    if width <= 0 or height <= 0:
        return [Tile(0, 0, 0, Region(0, 0, max(1, width), max(1, height)))]
    tile_size = max(32, int(tile_size))
    overlap = max(0.0, min(0.5, overlap))
    stride = max(1, int(tile_size * (1.0 - overlap)))

    def grid(n: int) -> int:
        if n <= tile_size:
            return 1
        return 1 + (n - tile_size + stride - 1) // stride

    rows, cols = grid(height), grid(width)
    while rows * cols > max_tiles:
        tile_size = int(tile_size * 1.25) + 1
        stride = max(1, int(tile_size * (1.0 - overlap)))
        rows, cols = grid(height), grid(width)

    tiles: list[Tile] = []
    index = 0
    for r in range(rows):
        for c in range(cols):
            left = min(c * stride, max(0, width - tile_size)) if c < cols - 1 else max(0, width - tile_size)
            top = min(r * stride, max(0, height - tile_size)) if r < rows - 1 else max(0, height - tile_size)
            tw = min(tile_size, width - left)
            th = min(tile_size, height - top)
            tiles.append(Tile(index=index, row=r, col=c, region=Region(left, top, tw, th)))
            index += 1
    return tiles


def crop_tile(decoded: DecodedImage, tile: Tile) -> Any:
    """Crop a tile out of a decoded image (PIL image)."""
    from .image import crop  # noqa: PLC0415

    return crop(decoded.image, tile.region)


def _iou(a: Region, b: Region) -> float:
    left = max(a.x, b.x)
    top = max(a.y, b.y)
    right = min(a.right, b.right)
    bottom = min(a.bottom, b.bottom)
    if right <= left or bottom <= top:
        return 0.0
    inter = (right - left) * (bottom - top)
    union = a.width * a.height + b.width * b.height - inter
    return inter / union if union > 0 else 0.0


def merge_observations(
    observations: list[VisualObservation],
    *,
    iou_threshold: float = 0.5,
) -> list[VisualObservation]:
    """Deduplicate observations from overlapping tiles.

    Two observations are considered the same element when their boxes overlap
    strongly AND their text agrees (case-insensitive). The survivor keeps the
    highest confidence and the union-ish box (the first, higher-confidence one).
    """
    merged: list[VisualObservation] = []
    for obs in observations:
        duplicate = False
        for kept in merged:
            if kept.region is None or obs.region is None:
                continue
            same_text = kept.text.strip().lower() == obs.text.strip().lower()
            if same_text and _iou(kept.region, obs.region) >= iou_threshold:
                if obs.confidence > kept.confidence:
                    kept.region = obs.region
                    kept.confidence = obs.confidence
                duplicate = True
                break
        if not duplicate:
            merged.append(obs)
    return merged


async def analyze_tiled(
    decoded: DecodedImage,
    *,
    analyzer: Callable[[Any, Tile], Awaitable[list[VisualObservation]]],
    tile_size: int,
    overlap: float = 0.1,
    max_tiles: int = 16,
    concurrency: int = 4,
) -> tuple[list[VisualObservation], list[Tile]]:
    """Analyze every tile in parallel and merge the results.

    `analyzer(pil_tile, tile)` returns that tile's observations with regions in
    ORIGINAL image coordinates (the caller offsets by `tile.region`).
    """
    tiles = plan_tiles(decoded.width, decoded.height, tile_size=tile_size, overlap=overlap, max_tiles=max_tiles)
    if len(tiles) <= 1:
        return await analyzer(decoded.image, tiles[0]), tiles

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run(tile: Tile) -> list[VisualObservation]:
        async with semaphore:
            try:
                return await analyzer(crop_tile(decoded, tile), tile)
            except Exception:  # noqa: BLE001 - one bad tile must not lose the rest
                return []

    results = await asyncio.gather(*(run(t) for t in tiles))
    flat = [obs for group in results for obs in group]
    return merge_observations(flat), tiles


__all__ = ["Tile", "plan_tiles", "crop_tile", "merge_observations", "analyze_tiled"]
