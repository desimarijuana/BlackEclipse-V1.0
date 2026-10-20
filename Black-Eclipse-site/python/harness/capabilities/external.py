"""The external capability lane: broker/API/MCP adapters are proposed, never granted.

A generated recipe is local code that runs in the analysis sandbox. An external
system is different: it has a network endpoint, a credential the operator holds,
and an activation decision no agent may make. This module produces the ONE typed
proposal for that lane. It reuses the existing MCP preset catalog and the
existing recovery acquisition vocabulary, and it never installs, enables or
stores a credential value.

The proposal is read-only. Credentials are named (vault secret names), never
valued. `present` says only whether a value exists; it is never the value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlparse

from ..recovery.acquisition import AcquisitionProposal, AcquisitionStep

EXTERNAL_KINDS: tuple[str, ...] = ("broker", "api", "mcp")
SURFACES: tuple[str, ...] = ("mcp_preset", "plugin", "mcp_server", "operator")
MCP_APPROVAL_KIND = "mcp_install"
PLUGIN_APPROVAL_KIND = "plugin_install"

_BROKER_WORDS = (
    "broker", "brokerage", "alpaca", "interactive brokers", "ibkr", "tradier",
    "binance", "coinbase", "kraken", "schwab", "robinhood", "etrade", "trading",
    "order", "orders", "positions", "holdings",
)
_MCP_WORDS = ("mcp", "model context protocol")


_SECRET_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")


def _looks_like_value(text: str) -> bool:
    """A credential-shaped string was supplied where a NAME belongs."""
    if not text:
        return False
    try:
        from ..eclipse_memory.decision import looks_like_credential_value  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - the shape guard is best-effort
        return False
    return looks_like_credential_value(text)


def _contains(text: str, words: Iterable[str]) -> bool:
    lowered = (text or "").lower()
    return any(word in lowered for word in words)


def classify_external(need: str, kind: str = "auto") -> str:
    """The external adapter kind, from an explicit value or the need's words."""
    explicit = (kind or "auto").strip().lower()
    if explicit in EXTERNAL_KINDS:
        return explicit
    text = need or ""
    if _contains(text, _MCP_WORDS):
        return "mcp"
    if _contains(text, _BROKER_WORDS):
        return "broker"
    return "api"


def _secret_names(values: Optional[Iterable[str]]) -> list[str]:
    names: list[str] = []
    for value in values or ():
        name = str(value or "").strip()
        if not name or name in names:
            continue
        if _looks_like_value(name):
            raise ValueError(
                "credential values are not accepted; supply vault secret NAMES only"
            )
        if not _SECRET_NAME.match(name):
            continue
        names.append(name)
    return names


def normalize_credential_names(values: Optional[Iterable[str]]) -> list[str]:
    """The public NAME-only normalization used by every adapter surface.

    A credential-shaped value is refused, never stored. This is the single
    validator for adapter authoring as well as external proposals.
    """
    return _secret_names(values)


def _present(
    name: str, resolver: Optional[Callable[[str], Optional[bool]]],
) -> Optional[bool]:
    if resolver is None:
        return None
    try:
        value = resolver(name)
    except Exception:  # noqa: BLE001 - a resolver failure is unknown, never "present"
        return None
    return None if value is None else bool(value)


@dataclass(frozen=True)
class CredentialRequirement:
    """A credential by NAME only. A value is never accepted by this contract."""

    name: str
    label: str = ""
    required: bool = True
    present: Optional[bool] = None
    source: str = "vault"  # vault | plugin | oauth

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label or self.name,
            "required": self.required,
            "present": self.present,
            "source": self.source,
        }


@dataclass
class ExternalProposal:
    need: str
    kind: str
    surface: str
    adapter_id: str = ""
    label: str = ""
    transport: str = ""
    oauth: bool = False
    credentials: list[CredentialRequirement] = field(default_factory=list)
    approval_kind: str = ""
    approval_digest: str = ""
    approval_gate: str = ""
    next_action: str = "operator"
    activation: str = "operator"
    enabled: bool = False
    installable: bool = False
    activation_ready: bool = False
    missing: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    acquisition: Optional[AcquisitionProposal] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "need": self.need,
            "kind": self.kind,
            "surface": self.surface,
            "adapterId": self.adapter_id,
            "label": self.label,
            "transport": self.transport,
            "oauth": self.oauth,
            "credentials": [item.to_dict() for item in self.credentials],
            "approval": {
                "required": True,
                "kind": self.approval_kind,
                "digest": self.approval_digest,
                "gate": self.approval_gate,
                "singleUse": self.approval_kind == MCP_APPROVAL_KIND,
            },
            "nextAction": self.next_action,
            "activation": self.activation,
            "enabled": self.enabled,
            "installable": self.installable,
            "activationReady": self.activation_ready,
            "missing": list(self.missing),
            "nextSteps": list(self.next_steps),
            "acquisition": self.acquisition.to_dict() if self.acquisition else None,
        }


def _approval_digest(kind: str, key: str) -> str:
    from ..mcp.install_tools import approval_digest  # noqa: PLC0415 - ONE digest authority

    return approval_digest(kind, key)


def _acquisition(
    need: str,
    *,
    adapter_id: str,
    surface: str,
    description: str,
    installable: bool,
    missing: list[str],
) -> AcquisitionProposal:
    """The same acquisition vocabulary the recovery lane executes.

    The install action names the existing gate; the enable action is always the
    operator's. No handler is invoked here.
    """
    install_surface = {
        "mcp_preset": "mcp",
        "plugin": "plugin",
    }.get(surface, "operator")
    return AcquisitionProposal(
        query=need,
        steps=[
            AcquisitionStep(
                action="install",
                description=description,
                capability_id=adapter_id or None,
                requires_approval=True,
                surface=install_surface,
                ready=installable,
                reason=(
                    "the adapter install is an operator-approved mutation"
                    if installable
                    else "no installer fits; an operator must supply the adapter surface"
                ),
                missing=tuple(missing),
            ),
            AcquisitionStep(
                action="enable",
                description=(
                    f"enable {adapter_id or 'the adapter'} only after its credentials "
                    "are set and its contract is reviewed"
                ),
                capability_id=adapter_id or None,
                requires_approval=True,
                surface="operator",
                ready=False,
                reason="activation stays an operator decision in Settings",
                missing=(),
            ),
        ],
        retry={
            "action": "resume_task",
            "from": "last_checkpoint",
            "taskId": None,
            "note": "resume the original task after the operator enables the adapter",
        },
    )


def _mcp_preset(
    need: str,
    spec: Any,
    secret_names: list[str],
    resolver: Optional[Callable[[str], Optional[bool]]],
) -> ExternalProposal:
    credentials: list[CredentialRequirement] = []
    if spec.secret_ref:
        credentials.append(CredentialRequirement(
            name=spec.secret_ref,
            label=spec.secret_label or spec.secret_ref,
            present=_present(spec.secret_ref, resolver),
        ))
    for name in secret_names:
        if any(item.name == name for item in credentials):
            continue
        credentials.append(CredentialRequirement(
            name=name, present=_present(name, resolver),
        ))
    missing = [
        f"vault secret {item.name!r} is not set"
        for item in credentials if item.present is False
    ]
    if spec.oauth:
        next_steps = [
            "approve the single-use mcp_install approval for this preset",
            "install writes a DISABLED config with no tools selected",
            "the operator enables it and completes the OAuth sign-in in Settings â†’ MCP",
            "resume the original task from its checkpoint after activation",
        ]
    else:
        next_steps = [
            "the operator sets the named vault secret(s); values never enter chat",
            "approve the single-use mcp_install approval for this preset",
            "install writes a DISABLED config with no tools selected",
            "the operator enables it and selects tools in Settings â†’ MCP",
            "resume the original task from its checkpoint after activation",
        ]
    if missing:
        next_steps.insert(0, "set the missing credential(s), then ask for the proposal again")
    activation_ready = (
        not spec.oauth
        and not missing
        and all(item.present is True for item in credentials)
    )
    return ExternalProposal(
        need=need,
        kind="mcp",
        surface="mcp_preset",
        adapter_id=spec.id,
        label=spec.label,
        transport=spec.transport,
        oauth=bool(spec.oauth),
        credentials=credentials,
        approval_kind=MCP_APPROVAL_KIND,
        approval_digest=_approval_digest(MCP_APPROVAL_KIND, spec.id),
        approval_gate="mcp_approval_store",
        next_action="mcp_install",
        installable=True,
        activation_ready=activation_ready,
        missing=missing,
        next_steps=next_steps,
        acquisition=_acquisition(
            need,
            adapter_id=spec.id,
            surface="mcp_preset",
            description=f"install the MCP preset {spec.id!r} as a disabled config",
            installable=True,
            missing=missing,
        ),
    )


def _plugin(
    need: str, plugin_path: str, secret_names: list[str],
) -> ExternalProposal:
    tail = plugin_path.replace("\\", "/").rstrip("/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", tail)
    adapter_id = name or "plugin"
    credentials = [
        CredentialRequirement(
            name=item, present=None, source="plugin",
        )
        for item in secret_names
    ]
    missing = [
        "the plugin install is an operator action; the plugin platform has not run it",
    ]
    next_steps = [
        "the operator installs the supplied plugin folder through the plugin platform",
        "the operator enters the named plugin secrets; values never enter chat",
        "the operator enables the plugin explicitly (nothing self-enables)",
        "resume the original task from its checkpoint after activation",
    ]
    return ExternalProposal(
        need=need,
        kind=classify_external(need, "auto"),
        surface="plugin",
        adapter_id=adapter_id,
        label=plugin_path,
        credentials=credentials,
        approval_kind=PLUGIN_APPROVAL_KIND,
        approval_digest=_approval_digest(PLUGIN_APPROVAL_KIND, plugin_path),
        approval_gate="plugin_platform_operator",
        next_action="operator",
        installable=True,
        activation_ready=False,
        missing=missing,
        next_steps=next_steps,
        acquisition=_acquisition(
            need,
            adapter_id=adapter_id,
            surface="plugin",
            description=f"install the plugin folder {plugin_path!r} disabled",
            installable=True,
            missing=missing,
        ),
    )


def _mcp_server(
    need: str,
    *,
    server_url: str,
    server_command: str,
    secret_names: list[str],
    resolver: Optional[Callable[[str], Optional[bool]]],
) -> ExternalProposal:
    credentials = [
        CredentialRequirement(
            name=item, present=_present(item, resolver),
        )
        for item in secret_names
    ]
    missing = [
        "the custom MCP server config is operator-supplied; no installer writes it",
    ]
    parsed = urlparse(server_url) if server_url else None
    unsafe_url = _looks_like_value(server_url)
    if parsed is not None and "@" in (parsed.netloc or ""):
        unsafe_url = True
    if unsafe_url:
        missing.append("credentials must not be embedded in the server URL")
        host = ""
    else:
        host = (parsed.hostname if parsed is not None else "") or ""
    unsafe_command = _looks_like_value(server_command)
    if unsafe_command:
        missing.append("credentials must not be embedded in the server command")
    if host:
        adapter_id = host
    elif server_command and not unsafe_command:
        adapter_id = server_command.split()[0]
    else:
        adapter_id = "mcp_server"
    next_steps = [
        "the operator adds the custom MCP server in Settings â†’ MCP (disabled at first)",
        "the operator sets the named vault secret(s); values never enter chat",
        "the operator enables it and selects tools explicitly (nothing self-enables)",
        "resume the original task from its checkpoint after activation",
    ]
    return ExternalProposal(
        need=need,
        kind="mcp",
        surface="mcp_server",
        adapter_id=adapter_id,
        label="" if unsafe_command else (host or server_command),
        transport="http" if server_url else "stdio",
        credentials=credentials,
        approval_kind="operator",
        approval_gate="operator_transport",
        installable=False,
        activation_ready=False,
        missing=missing,
        next_steps=next_steps,
        acquisition=_acquisition(
            need,
            adapter_id=adapter_id,
            surface="mcp_server",
            description="add a custom MCP server through the operator's Settings surface",
            installable=False,
            missing=missing,
        ),
    )


def _operator(
    need: str, kind: str, secret_names: list[str],
) -> ExternalProposal:
    credentials = [
        CredentialRequirement(name=item, present=None) for item in secret_names
    ]
    missing = [
        "an operator-supplied MCP preset id, plugin folder, or MCP endpoint/command",
    ]
    if not secret_names:
        missing.append("the credential names the adapter needs")
    next_steps = [
        "ask the operator for the adapter surface and credential NAMES (never values)",
        "call capability_external again with integrationId, pluginPath or serverUrl",
        "the operator approves the install; the operator enables it explicitly",
        "resume the original task from its checkpoint after activation",
    ]
    return ExternalProposal(
        need=need,
        kind=kind,
        surface="operator",
        credentials=credentials,
        approval_kind="operator",
        approval_gate="operator_transport",
        installable=False,
        activation_ready=False,
        missing=missing,
        next_steps=next_steps,
        acquisition=_acquisition(
            need,
            adapter_id="",
            surface="operator",
            description="choose an existing adapter surface with the operator",
            installable=False,
            missing=missing,
        ),
    )


def propose_external(
    need: str,
    *,
    kind: str = "auto",
    integration_id: str = "",
    plugin_path: str = "",
    server_url: str = "",
    server_command: str = "",
    credential_names: Optional[Iterable[str]] = None,
    secret_present: Optional[Callable[[str], Optional[bool]]] = None,
) -> ExternalProposal:
    """Propose the existing external surface for a need. Nothing is installed.

    `secret_present` answers only "is there a value for this NAME?"; it is never
    given a value and its answer is stored as a boolean. An unavailable resolver
    leaves presence unknown instead of guessing.
    """
    chosen = classify_external(need, kind)
    names = _secret_names(credential_names)
    integration_id = str(integration_id or "").strip()
    plugin_path = str(plugin_path or "").strip()
    server_url = str(server_url or "").strip()
    server_command = str(server_command or "").strip()

    if integration_id:
        from ..mcp.presets import integration as find_preset  # noqa: PLC0415

        spec = find_preset(integration_id)
        if spec is None:
            proposal = _operator(need, chosen, names)
            proposal.missing.insert(0, f"unknown MCP integration {integration_id!r}")
            proposal.next_steps.insert(
                0, "call mcp_integrations to list the preset catalog",
            )
            return proposal
        return _mcp_preset(need, spec, names, secret_present)
    if plugin_path:
        return _plugin(need, plugin_path, names)
    if server_url or server_command:
        return _mcp_server(
            need,
            server_url=server_url,
            server_command=server_command,
            secret_names=names,
            resolver=secret_present,
        )
    return _operator(need, chosen, names)


__all__ = [
    "CredentialRequirement",
    "EXTERNAL_KINDS",
    "ExternalProposal",
    "MCP_APPROVAL_KIND",
    "PLUGIN_APPROVAL_KIND",
    "SURFACES",
    "classify_external",
    "propose_external",
]
