"""The remote command vocabulary.

Two classes of message arrive on a channel:

  * a `/command` the gateway understands deterministically, and
  * free text, which is dispatched to the agent as a natural-language turn.

This module owns ONLY the vocabulary + parser. It never executes anything — the
dispatcher decides. The scope column is the MINIMUM scope a binding must hold; the
dispatcher re-checks it against the binding, so this table is documentation of
intent, not the authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedCommand:
    verb: str
    args: list[str]
    raw: str

    @property
    def is_command(self) -> bool:
        return bool(self.verb)


@dataclass(frozen=True)
class CommandSpec:
    name: str
    scope: str
    mutating: bool
    description: str


# The closed control-command table. `do` is the operator-only tool bridge.
COMMANDS: dict[str, CommandSpec] = {
    "start": CommandSpec("start", "viewer", False, "Show what this channel can do."),
    "help": CommandSpec("help", "viewer", False, "Show the command list."),
    "whoami": CommandSpec("whoami", "viewer", False, "Show your linked identity and scope."),
    "bindings": CommandSpec("bindings", "viewer", False, "List your linked accounts on this channel."),
    "link": CommandSpec("link", "viewer", False, "Link this account: /link <code>."),
    "unlink": CommandSpec("unlink", "viewer", False, "Unlink this account from Eclipse."),
    "run": CommandSpec("run", "assistant", False, "Run the agent on the rest of the line."),
    # `/do` is reachable at viewer scope for READ tools; the dispatcher raises the
    # bar to `operator` + an allowlist entry + `/confirm` for any mutating tool.
    "do": CommandSpec("do", "viewer", True, "Invoke a whitelisted tool: /do <tool> <json-args>."),
    # Explicit mutation verbs: always operator scope AND always confirmation-gated,
    # then executed as an agent turn with a directive. This is a STRONGER gate than
    # plain agent text, so a viewer/assistant can never trigger one.
    "trade": CommandSpec("trade", "operator", True, "Record a trade: /trade <details>."),
    "alert": CommandSpec("alert", "operator", True, "Create a price alert: /alert <details>."),
    "backtest": CommandSpec("backtest", "operator", True, "Run a backtest: /backtest <details>."),
    "confirm": CommandSpec("confirm", "operator", False, "Confirm a pending action: /confirm <token>."),
    "cancel": CommandSpec("cancel", "viewer", False, "Cancel a pending action: /cancel <token>."),
}

# Explicit mutation verbs that require the in-channel confirmation gate.
MUTATION_VERBS: tuple[str, ...] = ("trade", "alert", "backtest")

# Commands whose body must be split preserving the remainder verbatim.
_RAW_REST = {"run", "do", "trade", "alert", "backtest"}


def parse(text: str) -> ParsedCommand:
    """Parse a message into a verb + args. Non-slash text has an empty verb."""
    raw = str(text or "").strip()
    if not raw.startswith("/"):
        return ParsedCommand(verb="", args=[], raw=raw)
    body = raw[1:].strip()
    if not body:
        return ParsedCommand(verb="", args=[], raw=raw)
    head, _, rest = body.partition(" ")
    verb = head.split("@", 1)[0].strip().lower()  # strip a Telegram `@botname` suffix
    rest = rest.strip()
    if verb in _RAW_REST:
        return ParsedCommand(verb=verb, args=[rest] if rest else [], raw=raw)
    return ParsedCommand(verb=verb, args=rest.split() if rest else [], raw=raw)


def spec_for(verb: str) -> Optional[CommandSpec]:
    return COMMANDS.get(str(verb or "").lower())


def is_known(verb: str) -> bool:
    return str(verb or "").lower() in COMMANDS


def help_lines() -> list[str]:
    return [f"/{c.name} — {c.description}" for c in COMMANDS.values()]


def help_text() -> str:
    lines = [
        "Eclipse remote control has these commands:",
        *help_lines(),
        "",
        "Anything else you type is sent to the agent (assistant scope and above).",
        "A mutating action asks you to /confirm a token before it runs.",
    ]
    return "\n".join(lines)


__all__ = [
    "COMMANDS",
    "MUTATION_VERBS",
    "CommandSpec",
    "ParsedCommand",
    "help_lines",
    "help_text",
    "is_known",
    "parse",
    "spec_for",
]
