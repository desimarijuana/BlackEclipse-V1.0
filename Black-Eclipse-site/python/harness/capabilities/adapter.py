"""Author a DISABLED broker/API adapter draft — never install or enable it.

The capability builder writes pure recipes. An external adapter is a different
kind of artifact: it has a host endpoint, credentials and an activation decision
the operator owns. This module writes a reviewable plugin draft (manifest, code,
README) into `.black-eclipse/adapters/<slug>/`, validates the manifest with the
SAME plugin contract the loader uses, and stops there.

The draft:
  * names credentials only (never a value), and validates names with the shared
    external-lane normalizer;
  * is HTTPS-only, with no userinfo in the URL;
  * maps GET tools to `read` and POST tools to `external_action`;
  * declares only the `network` permission;
  * is NOT installed into the plugin platform and NOT enabled.

The operator still reviews the auth scheme, installs it through the plugin
surface, supplies the secrets and enables it explicitly.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

from .external import classify_external, normalize_credential_names

_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_TOOL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
_PATH = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]{0,199}$")
_MAX_TOOLS = 12
_MAX_CREDENTIALS = 8


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9-]+", "-", (value or "").strip().lower()).strip("-")
    text = re.sub(r"-{2,}", "-", text)[:64].strip("-")
    if not text or not _SLUG.match(text):
        raise ValueError("adapterId must lowercase letters, digits and hyphens")
    return text


def _derived_slug(base_url: str, kind: str) -> str:
    host = (urlparse(base_url).hostname or "").lower()
    labels = [part for part in host.split(".") if part and part not in ("www", "api")]
    stem = labels[0] if labels else kind
    return _slug(f"{stem}-{kind}")


def _base_url(value: str) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)
    if parsed.scheme != "https":
        raise ValueError("the adapter base URL must use https")
    if not parsed.hostname:
        raise ValueError("the adapter base URL has no host")
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise ValueError("credentials must not be embedded in the base URL")
    if parsed.query or parsed.fragment:
        raise ValueError("the adapter base URL must not include a query or fragment")
    return text.rstrip("/")


def _tools(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("at least one tool is required")
    if len(raw) > _MAX_TOOLS:
        raise ValueError(f"at most {_MAX_TOOLS} tools can be authored at once")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict):
            raise ValueError("each tool must be an object with a name")
        name = str(item.get("name") or "").strip()
        if not _TOOL_NAME.match(name):
            raise ValueError(f"invalid tool name: {name!r}")
        if name in seen:
            raise ValueError(f"duplicate tool name: {name!r}")
        seen.add(name)
        method = str(item.get("method") or "GET").strip().upper()
        if method not in ("GET", "POST"):
            raise ValueError(f"tool {name!r} must use GET or POST")
        path = str(item.get("path") or f"/{name.replace('_', '-')}").strip()
        if not _PATH.match(path):
            raise ValueError(f"tool {name!r} has an invalid path: {path!r}")
        description = str(item.get("description") or f"Call {name} on the adapter.")[:300]
        out.append({
            "name": name,
            "method": method,
            "path": path,
            "description": description,
        })
    return out


def _method_ident(name: str, used: set[str]) -> str:
    ident = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not ident or ident[0].isdigit():
        ident = f"tool_{ident}"
    candidate = ident
    index = 2
    while candidate in used:
        candidate = f"{ident}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def _plugin_source(tools: list[dict[str, str]], credentials: list[str]) -> str:
    lines = [
        '"""Generated adapter DRAFT. Disabled; review before installing."""',
        "",
        "from harness.plugins.sdk import Plugin, tool",
        "",
        "",
        "class AdapterPlugin(Plugin):",
        "    def _url(self, ctx, path):  # noqa: ANN001",
        '        base = str(ctx.config.get("baseUrl") or "").rstrip("/")',
        "        return base + path",
        "",
        "    def _headers(self, ctx):  # noqa: ANN001",
        '        headers = {"Accept": "application/json"}',
    ]
    if credentials:
        first = json.dumps(credentials[0])
        lines.extend([
            f"        token = ctx.config.get({first})",
            "        if token:",
            '            headers["Authorization"] = f"Bearer {token}"',
            "        # TODO(operator): confirm the auth scheme and header for this API.",
        ])
    lines.append("        return headers")
    lines.append("")
    used: set[str] = set()
    for item in tools:
        ident = _method_ident(item["name"], used)
        name = json.dumps(item["name"])
        description = json.dumps(item["description"])
        path = json.dumps(item["path"])
        lines.extend([
            "    @tool(",
            f"        name={name},",
            f"        description={description},",
            '        schema={"type": "object", "properties": {}, "additionalProperties": True},',
            "    )",
            f"    async def {ident}(self, args, ctx):  # noqa: ANN001",
            '        """Generated from the operator-supplied endpoint contract."""',
        ])
        call = "get" if item["method"] == "GET" else "post"
        extra = "params=args" if call == "get" else "json=args"
        lines.extend([
            f"        response = await ctx.http.{call}(",
            f"            self._url(ctx, {path}),",
            f"            {extra}, headers=self._headers(ctx),",
            "        )",
            "        return response.json()",
            "",
        ])
    lines.append("")
    lines.append("plugin = AdapterPlugin")
    lines.append("")
    return "\n".join(lines)


@dataclass
class AdapterDraft:
    adapter_id: str
    kind: str
    base_url: str
    directory: str
    files: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)
    credentials: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "drafted",
            "adapterId": self.adapter_id,
            "kind": self.kind,
            "baseUrl": self.base_url,
            "directory": self.directory,
            "files": list(self.files),
            "manifest": self.manifest,
            "credentials": list(self.credentials),
            "tools": list(self.tool_names),
            "installed": False,
            "enabled": False,
            "nextSteps": list(self.next_steps),
        }


def author_adapter(
    need: str,
    *,
    base_url: str,
    tools: Any,
    root: Path,
    adapter_id: str = "",
    kind: str = "auto",
    credential_names: Optional[Iterable[str]] = None,
    label: str = "",
) -> AdapterDraft:
    """Write a validated, disabled adapter draft. Nothing is installed/enabled.

    Raises `ValueError` for an invalid contract (the tool turns it into a named
    refusal). Existing drafts are never overwritten silently.
    """
    need_text = str(need or "").strip()
    if not need_text:
        raise ValueError("a description of the needed adapter is required")
    chosen = classify_external(need_text, kind)
    if chosen not in ("broker", "api"):
        raise ValueError(
            "this lane authors broker/API plugins; use the MCP surface for MCP servers"
        )
    base = _base_url(base_url)
    normalized_tools = _tools(tools)
    credentials = normalize_credential_names(credential_names)
    if len(credentials) > _MAX_CREDENTIALS:
        raise ValueError(f"at most {_MAX_CREDENTIALS} credential names are allowed")
    slug = _slug(adapter_id) if adapter_id else _derived_slug(base, chosen)
    directory = Path(root) / ".black-eclipse" / "adapters" / slug
    if directory.exists():
        raise ValueError(
            f"an adapter draft named {slug!r} already exists; choose another adapterId"
        )

    manifest: dict[str, Any] = {
        "id": slug,
        "name": label or f"{slug} adapter (draft)",
        "version": "0.1.0",
        "publisher": "black-eclipse",
        "category": "generated",
        "tags": ["draft", chosen],
        "description": f"Draft adapter: {need_text}"[:500],
        "runtime": {"type": "python", "entrypoint": "plugin:AdapterPlugin"},
        "permissions": ["network"],
        "contributes": {
            "tools": [
                {
                    "name": item["name"],
                    "description": item["description"],
                    "permission": "read" if item["method"] == "GET" else "external_action",
                }
                for item in normalized_tools
            ],
        },
        "configuration": [
            {
                "key": "baseUrl",
                "type": "string",
                "title": "Base URL",
                "description": "HTTPS endpoint for this adapter.",
                "default": base,
                "required": True,
            },
            *[
                {
                    "key": name,
                    "type": "secret",
                    "title": name,
                    "description": "Supplied by the operator; never stored in this draft.",
                    "required": True,
                }
                for name in credentials
            ],
        ],
        "authentication": {"type": "none"},
        "storage": {"kv": True},
    }

    # Validate with the SAME manifest contract the loader uses BEFORE writing.
    from ..plugins.manifest import PluginManifest  # noqa: PLC0415

    PluginManifest.model_validate(manifest)

    readme_lines = [
        f"# {manifest['name']}",
        "",
        "STATUS: DRAFT — not installed, not enabled.",
        "",
        f"Need: {need_text}",
        f"Endpoint: {base}",
        "",
        "## Tools",
        "",
    ]
    for item in normalized_tools:
        readme_lines.append(
            f"- `{item['name']}` — {item['method']} {item['path']} "
            f"({'read' if item['method'] == 'GET' else 'external action'})"
        )
    readme_lines.extend([
        "",
        "## Activation (operator-owned)",
        "",
        "1. Review `plugin.py` and `plugin.yaml`; confirm paths, methods and the",
        "   authentication scheme (the draft assumes a bearer token).",
        "2. Install the folder through the plugin platform, disabled.",
        "3. Set the named secrets in Settings; never paste a value into chat.",
        "4. Enable the plugin and select its tools explicitly.",
        "",
        "Credential names: " + (", ".join(credentials) if credentials else "none"),
        "",
    ])

    # Imported lazily: the harness ships PyYAML for the plugin loader.
    import yaml  # noqa: PLC0415

    directory.mkdir(parents=True, exist_ok=False)
    (directory / "plugin.py").write_text(
        _plugin_source(normalized_tools, credentials), encoding="utf-8",
    )
    (directory / "plugin.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8",
    )
    (directory / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")

    return AdapterDraft(
        adapter_id=slug,
        kind=chosen,
        base_url=base,
        directory=str(directory),
        files=["plugin.yaml", "plugin.py", "README.md"],
        manifest=manifest,
        credentials=credentials,
        tool_names=[item["name"] for item in normalized_tools],
        next_steps=[
            "review the draft code and manifest (authentication scheme included)",
            "the operator installs the folder through the plugin platform (disabled)",
            "the operator sets the named secrets; values never enter chat",
            "the operator enables it and selects tools explicitly; nothing self-enables",
        ],
    )


__all__ = ["AdapterDraft", "author_adapter"]
