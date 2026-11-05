"""Categorisation rules: deterministic, versioned, explainable.

A rule answers one question: given a statement line, which account should the
counter-entry hit? It never posts anything.

Deliberate properties:

  * **First match wins**, ordered by `(priority, name, version)`. Two runs over the
    same rows and the same rules always produce the same account — no sampling,
    no embeddings, no model call.
  * **All conditions inside a rule are ANDed**; the needles inside
    `payee_contains` are ORed (any one is enough).
  * **Amount bounds compare the MAGNITUDE**, so "over 100" means `|amount| > 100`
    for both an inflow and an outflow. The `direction` field picks the sign.
  * **A rule that cannot apply is skipped and SAID SO** (a missing/inactive target
    account, a regex that no longer compiles). It is never silently ignored.
  * **An unmatched row is not guessed.** It goes to the suspense account, and the
    import reports how many did.

Rules are append-only versions: editing a named rule creates the next version and
deactivates the previous one, so a historical import can still be explained by
the rule version that was live at the time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Optional, Sequence

from .errors import RULE_INVALID, LedgerError
from .importers import StatementRow
from .models import Account
from .money import ZERO

DIRECTIONS = ("IN", "OUT", "ANY")
SUSPENSE_ACCOUNT = "9999"


@dataclass(frozen=True)
class RuleMatch:
    payee_contains: tuple[str, ...] = ()
    payee_regex: str = ""
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    direction: str = "ANY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "payeeContains": list(self.payee_contains),
            "payeeRegex": self.payee_regex or None,
            "amountMin": None if self.amount_min is None else f"{self.amount_min:f}",
            "amountMax": None if self.amount_max is None else f"{self.amount_max:f}",
            "direction": self.direction,
        }


@dataclass
class CategorisationRule:
    id: str
    ledger_id: str
    name: str
    version: int
    priority: int
    match: RuleMatch
    target_account: str
    active: bool = True
    created_by: Optional[str] = None
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ledgerId": self.ledger_id,
            "name": self.name,
            "version": self.version,
            "priority": self.priority,
            "match": self.match.to_dict(),
            "targetAccount": self.target_account,
            "active": self.active,
            "createdBy": self.created_by,
            "createdAt": self.created_at,
        }


def build_rule(
    ledger_id: str,
    *,
    rule_id: str,
    name: str,
    target_account: str,
    priority: int = 100,
    payee_contains: Sequence[str] = (),
    payee_regex: str = "",
    amount_min: object = None,
    amount_max: object = None,
    direction: str = "ANY",
    version: int = 1,
    created_at: str = "",
) -> CategorisationRule:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise LedgerError(RULE_INVALID, "a rule needs a name", {})
    if len(clean_name) > 80:
        raise LedgerError(RULE_INVALID, "a rule name may be at most 80 characters",
                          {"name": clean_name})
    clean_target = str(target_account or "").strip()
    if not clean_target:
        raise LedgerError(RULE_INVALID, "a rule needs a `target_account`", {})
    needles = tuple(str(item).strip() for item in payee_contains if str(item).strip())
    pattern = str(payee_regex or "").strip()
    if pattern:
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise LedgerError(
                RULE_INVALID, f"`payee_regex` is not a valid regular expression: {exc}",
                {"pattern": pattern},
            ) from exc
    if not needles and not pattern and amount_min is None and amount_max is None:
        raise LedgerError(
            RULE_INVALID,
            "a rule needs at least one condition (payee match or amount bound); "
            "an unconditional rule would swallow every row",
            {},
        )
    low = _bound(amount_min, "amount_min")
    high = _bound(amount_max, "amount_max")
    if low is not None and high is not None and low > high:
        raise LedgerError(RULE_INVALID, "`amount_min` is greater than `amount_max`",
                          {"amountMin": f"{low:f}", "amountMax": f"{high:f}"})
    kind = str(direction or "ANY").strip().upper()
    if kind not in DIRECTIONS:
        raise LedgerError(RULE_INVALID, f"`direction` must be one of {', '.join(DIRECTIONS)}",
                          {"direction": str(direction)})
    try:
        order = int(priority)
    except (TypeError, ValueError) as exc:
        raise LedgerError(RULE_INVALID, "`priority` must be an integer",
                          {"priority": str(priority)}) from exc
    return CategorisationRule(
        id=rule_id,
        ledger_id=ledger_id,
        name=clean_name,
        version=int(version),
        priority=order,
        match=RuleMatch(
            payee_contains=needles, payee_regex=pattern,
            amount_min=low, amount_max=high, direction=kind,
        ),
        target_account=clean_target,
        created_at=created_at,
    )


def _bound(value: object, field_name: str) -> Optional[Decimal]:
    if value is None or str(value).strip() == "":
        return None
    from .money import D

    try:
        amount = D(value)
    except (ValueError, TypeError) as exc:
        raise LedgerError(RULE_INVALID, f"`{field_name}` is not a decimal literal",
                          {"field": field_name, "value": str(value)}) from exc
    if amount < ZERO:
        raise LedgerError(RULE_INVALID, f"`{field_name}` must be >= 0",
                          {"field": field_name, "value": str(value)})
    return amount


def rule_matches(rule: CategorisationRule, row: StatementRow) -> bool:
    match = rule.match
    amount = row.amount
    if match.direction == "IN" and amount <= ZERO:
        return False
    if match.direction == "OUT" and amount >= ZERO:
        return False
    magnitude = abs(amount)
    if match.amount_min is not None and magnitude < match.amount_min:
        return False
    if match.amount_max is not None and magnitude > match.amount_max:
        return False
    if match.payee_contains:
        haystack = row.description.casefold()
        if not any(needle.casefold() in haystack for needle in match.payee_contains):
            return False
    if match.payee_regex:
        try:
            if re.search(match.payee_regex, row.description, re.IGNORECASE) is None:
                return False
        except re.error:
            return False
    return True


def order_rules(rules: Iterable[CategorisationRule]) -> list[CategorisationRule]:
    """The ONE evaluation order: priority, then name, then version."""
    return sorted(
        (rule for rule in rules if rule.active),
        key=lambda rule: (rule.priority, rule.name.casefold(), rule.version),
    )


@dataclass
class Categorisation:
    account_code: str
    method: str
    rule_id: Optional[str] = None
    rule_name: Optional[str] = None
    rule_version: Optional[int] = None
    reason: str = ""
    skipped_rules: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accountCode": self.account_code,
            "method": self.method,
            "ruleId": self.rule_id,
            "ruleName": self.rule_name,
            "ruleVersion": self.rule_version,
            "reason": self.reason,
            "skippedRules": list(self.skipped_rules),
        }


def categorise(
    row: StatementRow,
    rules: Sequence[CategorisationRule],
    accounts_by_code: dict[str, Account],
    *,
    suspense_code: str = SUSPENSE_ACCOUNT,
) -> Categorisation:
    """First matching usable rule wins; otherwise SUSPENSE, never a guess."""
    skipped: list[dict[str, Any]] = []
    for rule in order_rules(rules):
        target = accounts_by_code.get(rule.target_account)
        if target is None:
            skipped.append({"ruleId": rule.id, "name": rule.name,
                            "reason": f"target account {rule.target_account} does not exist"})
            continue
        if not target.active:
            skipped.append({"ruleId": rule.id, "name": rule.name,
                            "reason": f"target account {rule.target_account} is inactive"})
            continue
        if rule_matches(rule, row):
            return Categorisation(
                account_code=rule.target_account,
                method="RULE",
                rule_id=rule.id,
                rule_name=rule.name,
                rule_version=rule.version,
                reason=f"matched rule {rule.name!r} v{rule.version}",
                skipped_rules=skipped,
            )
    return Categorisation(
        account_code=suspense_code,
        method="SUSPENSE",
        reason="no rule matched; parked in suspense for review",
        skipped_rules=skipped,
    )


__all__ = [
    "DIRECTIONS",
    "SUSPENSE_ACCOUNT",
    "Categorisation",
    "CategorisationRule",
    "RuleMatch",
    "build_rule",
    "categorise",
    "order_rules",
    "rule_matches",
]
