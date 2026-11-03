"""Period-end FX revaluation of monetary balances.

Every posting in a foreign-currency account already carries the rate used on the
day. Revaluation asks a different question: at the period-end rate, what is that
balance worth — and what entry trues the book up to it?

Only accounts **restricted to a foreign currency** (`account.currency` is set and
differs from the book's base currency) are candidates. An account in the base
currency has nothing to revalue, and an account with no currency restriction has
no single foreign balance to translate. That is a real limitation, stated rather
than papered over.

The rate is supplied. There is no rate provider in this module: a missing rate is
`RATE_REQUIRED` for that account and the account is skipped — never converted at
an invented rate, never at last period's rate silently.

Sign convention: `delta = target_base − current_base` on the account's own side.
A gain is where the account's base value moves in the owner's favour (an asset up,
a liability down); the counter-entry goes to the gain or loss account accordingly.

Idempotency: the external id embeds the account, the date AND the rate, so
re-running the same date at the same rate posts nothing, and a rate correction
produces one new entry that trues up the difference.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from .errors import REVALUATION_INVALID, RATE_REQUIRED, LedgerError
from .money import D, ZERO, q_money, q_rate

MONETARY_TYPES = ("ASSET", "LIABILITY")


def _candidates(service: Any, ledger_id: str) -> list[Any]:
    base = service._require(ledger_id).base_currency.upper()  # noqa: SLF001
    out = []
    for account in service.store.list_accounts(ledger_id):
        if account.type not in MONETARY_TYPES or not account.active:
            continue
        if not account.currency or account.currency.upper() == base:
            continue
        out.append(account)
    return out


def evaluate(
    service: Any,
    ledger_id: str,
    *,
    as_of: object,
    rates: dict[str, Any],
    gain_account: str,
    loss_account: str,
) -> list[dict[str, Any]]:
    try:
        when = date.fromisoformat(str(as_of)[:10]).isoformat()
    except ValueError as exc:
        raise LedgerError(REVALUATION_INVALID, "`as_of` must be an ISO date",
                          {"asOf": str(as_of)}) from exc
    if str(gain_account or "").strip() == str(loss_account or "").strip():
        raise LedgerError(REVALUATION_INVALID,
                          "`gain_account` and `loss_account` must differ", {})
    if not isinstance(rates, dict) or not rates:
        raise LedgerError(
            REVALUATION_INVALID,
            "`rates` must be an object of currency → rate (e.g. {\"EUR\": \"1.09\"})",
            {},
        )
    parsed_rates: dict[str, Decimal] = {}
    for currency, value in rates.items():
        try:
            rate = q_rate(D(value))
        except (ValueError, TypeError) as exc:
            raise LedgerError(REVALUATION_INVALID,
                              f"rate for {currency} is not a decimal",
                              {"currency": str(currency), "value": str(value)}) from exc
        if rate <= ZERO:
            raise LedgerError(REVALUATION_INVALID,
                              f"rate for {currency} must be > 0", {"currency": str(currency)})
        parsed_rates[str(currency).upper()] = rate

    items: list[dict[str, Any]] = []
    for account in _candidates(service, ledger_id):
        currency = account.currency.upper()
        postings = service.store.postings(ledger_id, account_code=account.code, end=when)
        # The FOREIGN balance counts only lines actually denominated in the
        # account's currency. A revaluation line is a base-currency adjustment and
        # is deliberately excluded, so re-running compounds nothing.
        foreign = sum(((row["debit"] or ZERO) - (row["credit"] or ZERO)
                       for row in postings
                       if str(row.get("currency") or "").upper() == currency), ZERO)
        current_base = sum(((row["baseDebit"] or ZERO) - (row["baseCredit"] or ZERO)
                            for row in postings), ZERO)
        supplied_rate = parsed_rates.get(currency)
        item: dict[str, Any] = {
            "accountCode": account.code,
            "currency": currency,
            "type": account.type,
            "date": when,
            "rate": None if supplied_rate is None else f"{supplied_rate:f}",
            "foreignBalance": f"{q_money(foreign):f}",
            "currentBase": f"{q_money(current_base):f}",
            "targetBase": None,
            "delta": None,
            "status": "NO_CHANGE",
            "entryId": None,
            "lines": [],
        }
        if foreign == ZERO and current_base == ZERO:
            item["status"] = "NO_BALANCE"
            items.append(item)
            continue
        rate = parsed_rates.get(currency)
        if rate is None:
            item["status"] = RATE_REQUIRED
            item["reason"] = f"no rate supplied for {currency}"
            items.append(item)
            continue
        target = q_money(foreign * rate)
        delta = q_money(target - current_base)
        item["targetBase"] = f"{target:f}"
        item["delta"] = f"{delta:f}"
        if delta == ZERO:
            items.append(item)
            continue
        # `net` is debit-positive for every account, so a POSITIVE delta always
        # moves the book in the owner's favour: an asset rose, or a liability
        # shrank. The counter-entry therefore follows the sign alone — no
        # per-account-type special case.
        gain_amount = delta
        magnitude = f"{abs(gain_amount):f}"
        if gain_amount > ZERO:
            lines = [
                {"account_code": account.code, "debit": magnitude, "base_only": True},
                {"account_code": str(gain_account).strip(), "credit": magnitude,
                 "base_only": True},
            ]
        else:
            lines = [
                {"account_code": str(loss_account).strip(), "debit": magnitude,
                 "base_only": True},
                {"account_code": account.code, "credit": magnitude, "base_only": True},
            ]
        item["status"] = "REVALUE"
        item["lines"] = lines
        item["externalId"] = f"fxrev:{account.code}:{when}:{rate:f}"
        items.append(item)
    return items


def preview(
    service: Any,
    ledger_id: str,
    *,
    as_of: object,
    rates: dict[str, Any],
    gain_account: str,
    loss_account: str,
    actor_id: Optional[str] = None,
) -> dict[str, Any]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    items = evaluate(service, ledger_id, as_of=as_of, rates=rates,
                      gain_account=gain_account, loss_account=loss_account)
    return {
        "mode": "preview",
        "ledgerId": ledger_id,
        "asOf": str(as_of)[:10],
        "items": items,
        "revalueCount": sum(1 for item in items if item["status"] == "REVALUE"),
        "rateRequired": [item["accountCode"] for item in items
                         if item["status"] == RATE_REQUIRED],
    }


def post(
    service: Any,
    ledger_id: str,
    *,
    as_of: object,
    rates: dict[str, Any],
    gain_account: str,
    loss_account: str,
    actor_id: Optional[str] = None,
) -> dict[str, Any]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    for code in (gain_account, loss_account):
        account = service.store.get_account(ledger_id, str(code).strip())
        if account is None or not account.active:
            raise LedgerError(REVALUATION_INVALID,
                              f"account {code!r} does not exist or is inactive",
                              {"accountCode": str(code)})
    items = evaluate(service, ledger_id, as_of=as_of, rates=rates,
                      gain_account=gain_account, loss_account=loss_account)
    posted: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for item in items:
        if item["status"] != "REVALUE":
            continue
        try:
            entry = service.post(
                ledger_id,
                entry_date=item["date"],
                lines=item["lines"],
                memo=f"FX revaluation {item['accountCode']} at {item['rate']}",
                source="revaluation",
                external_id=item["externalId"],
                actor_id=actor_id,
            )
        except LedgerError as exc:
            errors.append({"accountCode": item["accountCode"], "code": exc.code,
                           "message": exc.message})
            continue
        item["entryId"] = entry["id"]
        item["duplicate"] = bool(entry.get("duplicate"))
        posted.append(item)
    service.store.audit(
        ledger_id, "FX_REVALUATED", actor=actor_id,
        detail={"asOf": str(as_of)[:10], "posted": len(posted), "errors": len(errors)},
    )
    fresh = [item for item in posted if not item.get("duplicate")]
    return {
        "mode": "post",
        "ledgerId": ledger_id,
        "asOf": str(as_of)[:10],
        "items": items,
        "postedCount": len(fresh),
        "duplicateCount": len(posted) - len(fresh),
        "errorCount": len(errors),
        "posted": posted,
        "errors": errors,
        "rateRequired": [item["accountCode"] for item in items
                         if item["status"] == "RATE_REQUIRED"],
    }


__all__ = ["MONETARY_TYPES", "evaluate", "post", "preview"]
