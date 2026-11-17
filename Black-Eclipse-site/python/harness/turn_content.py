"""The human turn: text, attached documents, and reference images.

Extracted from `graph.py` (which is under a size ratchet) so the multimodal
turn assembly can grow without growing the agent graph. No behaviour lives here
beyond what `_build_messages` needs: `user_message` (text, used by budgeting) and
`user_content` (text or native content blocks, used by the HumanMessage).
"""

from __future__ import annotations

from typing import Any

from .schemas import RunRequest


def user_message(request: RunRequest) -> str:
    text = request.input.query
    if request.input.ticker:
        text += f"\n\nTicker: {request.input.ticker}"
    if request.input.market:
        text += f"\n\nMarket: {request.input.market}"
    documents = request.input.documents or []
    if documents:
        # Attached documents are user-provided context, not tool output: they
        # are wrapped and clearly attributed so the model can distinguish them
        # from authoritative JDdS data it retrieves itself. A shortened document
        # says so IN the turn, so the model can state the limit rather than
        # answering confidently from only the first part.
        parts = []
        for doc in documents:
            shortened = bool(getattr(doc, "truncated", False))
            attr = ' shortened="true"' if shortened else ""
            note = (
                "\n(This document was shortened to fit; you are reading its "
                "first part and must say so if the question depends on the "
                "rest.)\n"
                if shortened else ""
            )
            parts.append(f'<document name="{doc.name}"{attr}>{note}{doc.text}\n</document>')
        text += (
            "\n\nAttached documents (user-provided context; treat as evidence "
            "the user supplied, and do not claim to have retrieved them):\n"
            + "\n\n".join(parts)
        )
    return text


def user_content(request: RunRequest) -> Any:
    """The human turn: the text, plus any attached reference images as REAL parts.

    A caption alone cannot teach a shape. The images are sent as native content
    blocks (the provider decides whether it can see them), and the trailing text
    keeps the honesty rule in front of the model: a picture is guidance, never a
    quote.
    """
    text = user_message(request)
    images = getattr(request.input, "images", None) or []
    if not images:
        return text
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for image in images:
        parts.append({"type": "image_url", "image_url": {"url": image.data_url}})
        caption = str(getattr(image, "caption", "") or "").strip()
        if caption:
            parts.append({"type": "text", "text": f'Reference image caption: "{caption}"'})
    parts.append({
        "type": "text",
        "text": (
            "The images above are PATTERN GUIDANCE from the operator: they are not "
            "live market data, may be out of date, and must never be quoted as a "
            "price. When an image conflicts with the broker/JDdS data, the data wins."
        ),
    })
    return parts


__all__ = ["user_content", "user_message"]
