"""Response-contract tools — the model's read-back for `eclipse-response` blocks.

The block contract is OWNED by the TS renderer (`src/lib/response/contract.ts`);
these tools expose it to the agent over the ONE read-only data bridge, so the
model can:

  * `response_block_schema` — look up the EXACT field names for any block type,
    derived live from the contract, instead of inferring them; and
  * `response_validate` — validate a drafted answer BEFORE emitting it and get
    per-block errors back (wrong field name, invalid value, malformed JSON).

Read-only, low-risk and bounded. A missing bridge or a transport failure returns
an explicit UNAVAILABLE — never a fabricated verdict.
"""

from __future__ import annotations

from typing import Any

from .tools import ToolContext, ToolDefinition, ToolRegistry

_MAX_VALIDATE_CHARS = 200_000


def _fmt_schema(payload: dict[str, Any]) -> str:
    blocks = payload.get("blocks") or []
    if not blocks:
        return (
            "No block matched that block_type. Call again WITHOUT `block_type` for "
            "the full list of registered types and their fields."
        )
    lines = [
        "eclipse-response block fields (exact names; `?` marks an optional field; "
        "one-line `{…}` lists an array item's fields — do not invent names):",
    ]
    for block in blocks:
        parts: list[str] = []
        for field in block.get("fields") or []:
            name = str(field.get("name"))
            kind = str(field.get("kind") or "value")
            items = field.get("itemFields")
            detail = f"{kind} {{{','.join(str(i) for i in items)}}}" if items else kind
            parts.append(f"{name}{'' if field.get('required') else '?'} ({detail})")
        lines.append(f"- {block.get('type')}: " + ", ".join(parts))
    icon_keys = [str(k) for k in payload.get("iconKeys") or []]
    if icon_keys:
        lines.append(
            "`icon` fields (kind `icon-key`, including inside array items) accept "
            "exactly one of: " + ", ".join(icon_keys) + ". Use one of these exact "
            "keys — never an emoji, component name, import path or made-up name."
        )
    return "\n".join(lines)


def _fmt_validation(payload: dict[str, Any]) -> str:
    if payload.get("error") and not payload.get("blocks"):
        return f"Response check could not run: {payload.get('error')}"
    blocks = payload.get("blocks") or []
    if payload.get("ok"):
        names = ", ".join(str(b.get("type")) for b in blocks)
        return f"OK — {len(blocks)} block(s) validated and will render: {names}."
    failed = [b for b in blocks if not b.get("ok")]
    lines = [
        f"NOT OK — {len(failed)} of {len(blocks)} block(s) would fail to render "
        "(everything else is fine):"
    ]
    for block in failed:
        lines.append(
            f"- block #{block.get('index')} `{block.get('type')}`: "
            f"{block.get('error') or 'invalid block'}"
        )
    for diag in payload.get("diagnostics") or []:
        if diag.get("blockIndex") is None:
            lines.append(f"- envelope: {diag.get('code')}: {diag.get('message')}")
    lines.append(
        "Fix ONLY the listed blocks (keep every other block and the JSON valid), "
        "then call response_validate again before sending the answer."
    )
    return "\n".join(lines)


async def response_block_schema(args: dict[str, Any], ctx: ToolContext) -> str:
    block_type = str(args.get("block_type") or "").strip()
    if ctx.data_bridge is None:
        return "UNAVAILABLE — the response-format schema is not reachable this run (no data bridge)."
    payload = await ctx.data_bridge.fetch(
        "response_contract", {"op": "schema", "block_type": block_type}
    )
    if payload.get("status") != "OK":
        return f"UNAVAILABLE — schema lookup failed: {payload.get('error', 'unknown error')}"
    return _fmt_schema(payload)


async def response_validate(args: dict[str, Any], ctx: ToolContext) -> str:
    markdown = str(args.get("markdown") or "")
    if not markdown.strip():
        return "Nothing to validate — pass the draft text that contains your ```eclipse-response fence (or the bare JSON payload)."
    if len(markdown) > _MAX_VALIDATE_CHARS:
        return "NOT CHECKED — payload is too large to validate; trim it and re-send."
    if ctx.data_bridge is None:
        return "UNAVAILABLE — the response-format check is not reachable this run (no data bridge)."
    payload = await ctx.data_bridge.fetch(
        "response_contract", {"op": "validate", "markdown": markdown}
    )
    if payload.get("status") != "OK":
        return f"UNAVAILABLE — validation failed: {payload.get('error', 'unknown error')}"
    return _fmt_validation(payload)


def register_response_contract_tools(registry: ToolRegistry) -> None:
    """Register the response-contract read-back tools on the ONE registry."""
    registry.register(
        ToolDefinition(
            name="response_block_schema",
            description=(
                "Look up the EXACT field names the eclipse-response renderer accepts, "
                "before emitting structured/visual blocks — never guess a field name. "
                "Also returns the live `icon` key vocabulary: an `icon` field (including "
                "inside array items) must use one of those semantic keys. "
                "Pass `block_type` for one type, or omit it for every registered type."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "block_type": {
                        "type": "string",
                        "description": "Block type, e.g. data_table, key_value, mermaid, gauge.",
                    },
                },
            },
            handler=response_block_schema,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="response_validate",
            description=(
                "Validate a drafted eclipse-response payload BEFORE sending it: pass the "
                "full text containing your ```eclipse-response fence (or the bare JSON). "
                "Returns per-block errors (wrong field names, invalid values, malformed "
                "JSON) so a drifted block is fixed in-turn instead of silently failing to "
                "render. This runs the renderer's own parser."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "markdown": {
                        "type": "string",
                        "description": "The drafted answer text (with the fence) or the bare JSON payload.",
                    },
                },
                "required": ["markdown"],
            },
            handler=response_validate,
            permission="read",
            risk="low",
            timeout_ms=15_000,
        )
    )


__all__ = ["register_response_contract_tools"]
