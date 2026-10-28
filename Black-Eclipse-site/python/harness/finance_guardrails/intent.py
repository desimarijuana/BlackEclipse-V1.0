"""Turn a tool call into a normalized `MoneyIntent` (or None).

This is the ONLY place that knows how different capabilities express a money
action. A tool the module does not recognize as money-moving yields `None` and
is untouched by the guardrail — the layer never invents authority or intent.

Recognition is deliberately conservative: the action verb must be present in a
tool-specific field or in the visible text (a click label, a command). A mere
argument called `amount` on a data tool is not a money movement.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .models import (
    CHANNEL_BROWSER,
    CHANNEL_COMPUTER,
    CHANNEL_MCP,
    CHANNEL_NATIVE,
    CHANNEL_SHELL,
    MONEY_ACTIONS,
    MoneyIntent,
)

# Tool → channel for the capabilities that can perform a money movement.
_COMPUTER_FINANCE_TOOLS = frozenset({"computer_finance_prepare"})
_COMPUTER_UI_TOOLS = frozenset({"computer_use"})
_BROWSER_CLICK_TOOLS = frozenset({"browser_click", "browser_visual_click"})
_SHELL_TOOLS = frozenset({"terminal_run", "shell_run", "command_run"})
#: The shell/terminal tool names the guardrail owns at the authorizer seam.
SHELL_TOOLS = _SHELL_TOOLS

_ACTION_SYNONYMS: dict[str, str] = {
    "buy": "buy", "purchase": "buy",
    "sell": "sell",
    "short": "short",
    "cover": "cover",
    "submit order": "submit_order", "place order": "place_order",
    "place_order": "place_order",
    "cancel order": "cancel_order", "cancel_order": "cancel_order",
    "modify order": "modify_order", "modify_order": "modify_order",
    "prepare order": "prepare_order", "prepare_order": "prepare_order",
    "transfer": "transfer", "send money": "send", "send payment": "payment",
    "withdraw": "withdraw", "withdrawal": "withdraw",
    "deposit": "deposit",
    "pay": "payment", "payment": "payment", "checkout": "payment",
    "wire": "transfer", "remit": "transfer",
}

# Text that, together with a recognized verb, identifies a broker/payment surface.
_FINANCIAL_SURFACE_TOKENS = (
    "broker", "brokerage", "trading", "trade ticket", "order ticket",
    "portfolio", "account balance", "bank", "wallet", "crypto", "exchange",
)

_NUMBER_RE = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?![\w.])")
_QTY_AT_PRICE_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(?:shares?|units?|contracts?|coins?|tokens?)?\s*"
    r"(?:(?:of|in)\s+)?(?:[A-Za-z][\w.-]*\s+)?"
    r"(?:at|@)\s*\$?\s*(\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)


def _number(text: str) -> Optional[float]:
    if not text:
        return None
    match = _NUMBER_RE.search(str(text).replace("$", " "))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _maybe_amount(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _amount_from_args(args: dict[str, Any]) -> Optional[float]:
    for key in ("notional", "amount", "value", "total", "price_total"):
        found = _maybe_amount(args.get(key))
        if found is not None:
            return found
    quantity = _maybe_amount(args.get("quantity") or args.get("qty") or args.get("shares"))
    price = _maybe_amount(args.get("price") or args.get("limit_price"))
    if quantity is not None and price is not None:
        return abs(quantity * price)
    return None


def _amount_from_text(text: str) -> Optional[float]:
    if not text:
        return None
    qty_at_price = _QTY_AT_PRICE_RE.search(text)
    if qty_at_price:
        try:
            qty = float(qty_at_price.group(1).replace(",", ""))
            price = float(qty_at_price.group(2).replace(",", ""))
            return abs(qty * price)
        except ValueError:
            pass
    amount_match = re.search(
        r"(?:\$|usd\s*|usdt\s*|eur\s*|gbp\s*)(\d[\d,]*(?:\.\d+)?)", text, re.IGNORECASE
    )
    if amount_match:
        try:
            return float(amount_match.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def detect_action(*texts: Any) -> Optional[str]:
    """The canonical money verb present in any of `texts`, or None."""
    blob = " ".join(str(t) for t in texts if t).lower().replace("-", " ").replace("_", " ")
    if not blob.strip():
        return None
    # Multi-word synonyms first so "submit order" is not read as "submit".
    for synonym in sorted(_ACTION_SYNONYMS, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(synonym)}(?!\w)", blob):
            return _ACTION_SYNONYMS[synonym]
    return None


def _counterparty_from_args(args: dict[str, Any]) -> Optional[str]:
    for key in (
        "counterparty", "recipient", "to", "destination", "address", "wallet",
        "beneficiary", "payee", "iban", "account_number",
    ):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:160]
    return None


def _instrument_from_args(args: dict[str, Any]) -> Optional[str]:
    for key in ("instrument", "symbol", "ticker", "asset", "pair"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()[:32]
    return None


def intent_from_tool(
    name: str,
    args: dict[str, Any],
    *,
    effect: Optional[str] = None,
    run_id: str = "",
    text: str = "",
) -> Optional[MoneyIntent]:
    """Assemble a `MoneyIntent` from a tool call, or None when it isn't one."""
    args = dict(args or {})
    name = str(name or "")
    visible = " ".join(
        str(v) for k, v in args.items()
        if k in ("target", "name", "text", "value", "label", "intent", "command", "description", "query")
        and isinstance(v, (str, int, float))
    )
    visible = f"{text} {visible}".strip()

    # ── Computer Use ─────────────────────────────────────────────────────────
    if name in _COMPUTER_FINANCE_TOOLS:
        action = detect_action(args.get("action"))
        return MoneyIntent(
            action=action or "prepare_order",
            tool=name, channel=CHANNEL_COMPUTER,
            amount=_amount_from_args(args),
            instrument=_instrument_from_args(args),
            account=str(args.get("account") or "") or None,
            run_id=run_id, source_text=visible, args=args,
        )
    if name in _COMPUTER_UI_TOOLS:
        action = detect_action(
            args.get("action"), args.get("target"), args.get("name"), args.get("text"),
            args.get("value"), args.get("intent"), text,
        )
        if action is None:
            return None
        return MoneyIntent(
            action=action, tool=name, channel=CHANNEL_COMPUTER,
            amount=_amount_from_text(visible) or _amount_from_args(args),
            counterparty=_counterparty_from_args(args),
            instrument=_instrument_from_args(args),
            account=str(args.get("account") or "") or None,
            run_id=run_id, source_text=visible, args=args,
        )

    # ── Browser ──────────────────────────────────────────────────────────────
    if name in _BROWSER_CLICK_TOOLS:
        action = detect_action(args.get("target"), args.get("text"), args.get("label"), text)
        if action is None:
            return None
        return MoneyIntent(
            action=action, tool=name, channel=CHANNEL_BROWSER,
            amount=_amount_from_text(visible) or _amount_from_args(args),
            counterparty=_counterparty_from_args(args),
            instrument=_instrument_from_args(args),
            run_id=run_id, source_text=visible, args=args,
        )

    # ── Shell / terminal ─────────────────────────────────────────────────────
    if name in _SHELL_TOOLS:
        command = str(args.get("command") or args.get("cmd") or text or "")
        lowered = command.lower()
        if not any(tok in lowered for tok in _FINANCIAL_SURFACE_TOKENS + (
            "/order", "/trade", "/transfer", "/withdraw", "/payment", "api.binance",
            "api.alpaca", "api.coinbase", "paypal", "stripe.com", "wise.com",
        )):
            return None
        action = detect_action(command)
        if action is None:
            return None
        return MoneyIntent(
            action=action, tool=name, channel=CHANNEL_SHELL,
            amount=_amount_from_text(command), run_id=run_id,
            source_text=command, args=args,
        )

    # ── MCP / generic external action ────────────────────────────────────────
    meta = args.pop("__effect_metadata__", None) or {}
    if effect in ("external_action", "write") or name.startswith("mcp__") or meta:
        action = detect_action(
            name.replace("_", " "), args.get("action"), args.get("type"),
            args.get("side"), args.get("operation"), text,
        )
        if action is None:
            return None
        return MoneyIntent(
            action=action, tool=name, channel=CHANNEL_MCP,
            amount=_amount_from_args(args) or _amount_from_text(visible),
            counterparty=_counterparty_from_args(args),
            instrument=_instrument_from_args(args),
            account=str(args.get("account") or args.get("account_id") or "") or None,
            run_id=run_id, source_text=visible, args=args,
        )

    return None


def intent_from_payload(payload: dict[str, Any]) -> Optional[MoneyIntent]:
    """Build an intent directly from a route/UI payload (operator evaluation)."""
    action = detect_action(payload.get("action"), payload.get("type"))
    if action is None:
        return None
    return MoneyIntent(
        action=action,
        tool=str(payload.get("tool") or ""),
        channel=str(payload.get("channel") or CHANNEL_NATIVE),
        amount=_maybe_amount(payload.get("amount")),
        currency=str(payload.get("currency") or "USD"),
        counterparty=str(payload.get("counterparty") or "") or None,
        instrument=str(payload.get("instrument") or "") or None,
        account=str(payload.get("account") or "") or None,
        source_text=str(payload.get("text") or ""),
        args=payload,
    )


def is_money_action(action: str) -> bool:
    return str(action or "").lower() in MONEY_ACTIONS


__all__ = [
    "SHELL_TOOLS", "detect_action", "intent_from_payload", "intent_from_tool",
    "is_money_action",
]
