"""Create deterministic sample assets for the Graph Studio media demo.

Run through `scripts/seed-graph-media-demo.mts`; it prints ONE JSON object and
nothing else so the seeder can consume it.

Assets are stored through the SAME stores the runtime uses:
  * the CSV in the bounded `HarnessGraphAsset` (owner `local`);
  * two candle images in the vision `VisionAssetStore` (owner `local`).
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.graph_runtime.assets import GraphAssetStore  # noqa: E402
from harness.persistence import AgentMemoryStore  # noqa: E402
from harness.vision.image import decode_bytes  # noqa: E402
from harness.vision.storage import VisionAssetStore  # noqa: E402


def _csv() -> bytes:
    lines = ["date,open,high,low,close,volume"]
    base = 100.0
    for index in range(24):
        opened = base + (index % 5) * 0.4
        close = opened + (0.9 if index % 3 else -0.7)
        high = max(opened, close) + 0.6
        low = min(opened, close) - 0.6
        lines.append(
            f"2026-01-{index + 1:02d},{opened:.2f},{high:.2f},{low:.2f},{close:.2f},"
            f"{1000 + index * 37}"
        )
        base = close
    return ("\n".join(lines) + "\n").encode("utf-8")


def _candles(option: str, bullish: bool) -> bytes:
    from PIL import Image, ImageDraw

    width, height = 640, 360
    image = Image.new("RGB", (width, height), (16, 18, 24))
    draw = ImageDraw.Draw(image)
    draw.text((16, 12), f"Candle option {option}", fill=(226, 232, 240))
    draw.text((16, 30), "reference setup — synthetic demo image", fill=(148, 163, 184))

    count = 9
    left, right, top, bottom = 48, width - 32, 70, height - 40
    step = (right - left) / count
    mid = (top + bottom) / 2
    for index in range(count):
        x = left + step * index + step / 2
        drift = (index - count / 2) * (3 if bullish else -1)
        opened = mid + drift + (6 if index % 2 else -6)
        close = opened + (18 if (index + (0 if bullish else 1)) % 3 else -14)
        high = max(opened, close) + 12
        low = min(opened, close) - 12
        color = (47, 191, 113) if close >= opened else (224, 82, 82)
        body = 14
        draw.line((x, high, x, low), fill=color, width=3)
        if abs(close - opened) < 4:
            draw.line((x - 8, opened, x + 8, opened), fill=color, width=3)
        else:
            draw.rectangle((x - body / 2, min(opened, close), x + body / 2, max(opened, close)), fill=color)

    draw.line((left, bottom, right, bottom), fill=(51, 65, 85), width=1)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def main() -> None:
    store = AgentMemoryStore()
    graph_assets = GraphAssetStore(store)
    vision_assets = VisionAssetStore(store)

    file_meta = graph_assets.save(
        "demo-bars.csv", _csv(), mime="text/csv", owner="local",
    )
    image_ids: list[str] = []
    for option, bullish in (("A", True), ("B", False)):
        data = _candles(option, bullish)
        decoded = decode_bytes(data, source=f"demo-candle-{option}.png", expected_mime="image/png")
        asset = vision_assets.save(
            decoded, source_kind="demo", source_ref=f"demo-candle-{option}.png",
            metadata={"name": f"candle-option-{option}.png"}, owner="local",
        )
        image_ids.append(asset.asset_id)

    print(json.dumps({
        "fileAssetId": file_meta["assetId"],
        "fileRef": file_meta["ref"],
        "fileName": file_meta["name"],
        "imageAssetIds": image_ids,
    }))


if __name__ == "__main__":
    main()
