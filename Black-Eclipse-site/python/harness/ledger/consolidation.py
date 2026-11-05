"""Group consolidation: member books → one set of statements, intercompany removed.

The model is deliberately small and explicit:

  * A **group** names member ledgers and the percentage of each to include.
  * Consolidation sums each member's account nets, scaled by ownership and by a
    supplied translation rate when the member's currency differs from the group's.
  * Accounts are matched **by code** and must agree on their TYPE; a code that is
    an asset in one member and a liability in another is a conflict, not a number
    to average.
  * **Intercompany pairs are eliminated by subtype** (`INTERCOMPANY_RECEIVABLE`
    vs `INTERCOMPANY_PAYABLE`, `INTERCOMPANY_REVENUE` vs `INTERCOMPANY_EXPENSE`).
    Only the matched amount is eliminated; an unmatched remainder stays in the
    consolidated books and is reported as a finding. Nothing is force-balanced.
  * The consolidated figures are handed to the SAME statement engine as a single
    ledger, so the accounting equation is checked once, in one place.

Method, stated plainly: this is **proportionate** consolidation. A member held at
80% contributes 80% of every line; there is no non-controlling-interest line and no
full-consolidation-with-NCI treatment. Translation uses ONE rate per currency for
all accounts (no average-rate P&L vs closing-rate balance-sheet split).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Optional, Sequence

from . import statements as stmts
from .errors import (
    ACCOUNT_TYPE_CONFLICT,
    GROUP_INVALID,
    GROUP_NOT_FOUND,
    MEMBER_EXISTS,
    MEMBER_LEDGER_MISSING,
    RATE_REQUIRED,
    LedgerError,
)
from .group_store import new_id
from .models import Account
from .money import D, ZERO, q_money, q_rate

BS_PAIR = ("INTERCOMPANY_RECEIVABLE", "INTERCOMPANY_PAYABLE")
# A revenue balance is a CREDIT (negative net) and an expense a DEBIT, so the
# P&L pair is stated debit-side first, exactly like the balance-sheet pair.
PL_PAIR = ("INTERCOMPANY_EXPENSE", "INTERCOMPANY_REVENUE")


@dataclass
class Elimination:
    kind: str
    amount: Decimal
    debit_accounts: list[tuple[str, Decimal]]
    credit_accounts: list[tuple[str, Decimal]]
    matched: Decimal
    unmatched: Decimal

    def postings(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for code, amount in self.debit_accounts:
            rows.append({"accountCode": code, "baseDebit": amount, "baseCredit": ZERO})
        for code, amount in self.credit_accounts:
            rows.append({"accountCode": code, "baseDebit": ZERO, "baseCredit": amount})
        return rows

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "amount": f"{q_money(self.amount):f}",
            "matched": f"{q_money(self.matched):f}",
            "unmatched": f"{q_money(self.unmatched):f}",
            "debitAccounts": [{"code": code, "amount": f"{q_money(value):f}"}
                              for code, value in self.debit_accounts],
            "creditAccounts": [{"code": code, "amount": f"{q_money(value):f}"}
                               for code, value in self.credit_accounts],
            "balanced": sum((value for _, value in self.debit_accounts), ZERO)
            == sum((value for _, value in self.credit_accounts), ZERO),
        }


class ConsolidationService:
    def __init__(self, ledger: Any) -> None:
        self.ledger = ledger

    # ── groups ───────────────────────────────────────────────────────────────
    def create_group(self, name: str, *, base_currency: str = "USD",
                     owner_id: Optional[str] = None, notes: Optional[str] = None,
                     actor: Optional[str] = None) -> dict[str, Any]:
        clean = str(name or "").strip()
        if not clean:
            raise LedgerError(GROUP_INVALID, "a group needs a name", {})
        currency = str(base_currency or "USD").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise LedgerError(GROUP_INVALID, "`base_currency` must be a 3-letter code",
                              {"baseCurrency": currency})
        group_id = new_id("grp")
        return self.ledger.groups.create_group(
            group_id, clean, base_currency=currency, owner_id=owner_id, notes=notes
        )

    def list_groups(self, owner_id: Optional[str] = None) -> list[dict[str, Any]]:
        rows = self.ledger.groups.list_groups(owner_id)
        for row in rows:
            row["members"] = self.ledger.groups.list_members(row["id"])
        return rows

    def add_member(self, group_id: str, ledger_id: str, *,
                   ownership_pct: object = "100",
                   actor_id: Optional[str] = None) -> dict[str, Any]:
        group = self._require_group(group_id)
        member_ledger = self.ledger.store.get_ledger(str(ledger_id))
        if member_ledger is None:
            raise LedgerError(MEMBER_LEDGER_MISSING,
                              f"ledger {ledger_id} does not exist",
                              {"ledgerId": str(ledger_id)})
        if self.ledger.groups.get_member(group["id"], member_ledger.id) is not None:
            raise LedgerError(MEMBER_EXISTS,
                              f"{member_ledger.name!r} is already in {group['name']!r}",
                              {"groupId": group["id"], "ledgerId": member_ledger.id})
        try:
            pct = q_rate(D(ownership_pct if ownership_pct not in (None, "") else "100"))
        except (ValueError, TypeError) as exc:
            raise LedgerError(GROUP_INVALID, "`ownership_pct` must be a decimal", {}) from exc
        if pct <= ZERO or pct > Decimal(100):
            raise LedgerError(GROUP_INVALID, "`ownership_pct` must be > 0 and <= 100",
                              {"ownershipPct": f"{pct:f}"})
        record = self.ledger.groups.add_member(new_id("gmb"), group["id"],
                                               member_ledger.id, f"{pct:f}")
        # The audit trail is per-ledger (the table's FK is a ledger), so a
        # membership change is recorded on the member it concerns.
        self.ledger.store.audit(member_ledger.id, "GROUP_MEMBER_ADDED",
                                subject_id=group["id"], actor=actor_id,
                                detail={"groupId": group["id"],
                                        "ownershipPct": f"{pct:f}"})
        return record

    def _require_group(self, group_id: str) -> dict[str, Any]:
        group = self.ledger.groups.get_group(str(group_id))
        if group is None:
            raise LedgerError(GROUP_NOT_FOUND, f"group {group_id} not found",
                              {"groupId": str(group_id)})
        return group

    # ── consolidation ────────────────────────────────────────────────────────
    def consolidate(self, group_id: str, *, as_of: object = None,
                    start: object = None, rates: Optional[dict[str, Any]] = None,
                    actor_id: Optional[str] = None) -> dict[str, Any]:
        group = self._require_group(group_id)
        members = self.ledger.groups.list_members(group["id"])
        if not members:
            raise LedgerError(GROUP_INVALID,
                              f"group {group['name']!r} has no members",
                              {"groupId": group["id"]})
        try:
            when = date.fromisoformat(str(as_of)[:10]) if as_of else date.today()
        except ValueError as exc:
            raise LedgerError(GROUP_INVALID, "`as_of` must be an ISO date",
                              {"asOf": str(as_of)}) from exc
        start_iso: Optional[str] = None
        if start not in (None, ""):
            try:
                start_iso = date.fromisoformat(str(start)[:10]).isoformat()
            except ValueError as exc:
                raise LedgerError(GROUP_INVALID, "`start` must be an ISO date",
                                  {"start": str(start)}) from exc
            if start_iso > when.isoformat():
                raise LedgerError(GROUP_INVALID, "`start` is after `as_of`",
                                  {"start": start_iso, "asOf": when.isoformat()})
        parsed_rates: dict[str, Decimal] = {}
        for currency, value in (rates or {}).items():
            try:
                parsed_rates[str(currency).upper()] = q_rate(D(value))
            except (ValueError, TypeError) as exc:
                raise LedgerError(GROUP_INVALID,
                                  f"rate for {currency} is not a decimal",
                                  {"currency": str(currency)}) from exc

        group_currency = group["baseCurrency"].upper()
        findings: list[dict[str, Any]] = []
        totals: dict[str, Decimal] = {}
        period_totals: dict[str, Decimal] = {}
        accounts_by_code: dict[str, Account] = {}
        member_rows: list[dict[str, Any]] = []

        for member in members:
            member_ledger = self.ledger.store.get_ledger(member["ledgerId"])
            if member_ledger is None:
                findings.append(self._finding(
                    MEMBER_LEDGER_MISSING, "blocker",
                    f"member ledger {member['ledgerId']} no longer exists",
                ))
                member_rows.append({"ledgerId": member["ledgerId"], "included": False,
                                    "reason": "ledger missing"})
                continue
            try:
                pct = D(member["ownershipPct"]) / Decimal(100)
            except (ValueError, TypeError):
                pct = Decimal(1)
            rate = Decimal(1)
            if member_ledger.base_currency.upper() != group_currency:
                rate = parsed_rates.get(member_ledger.base_currency.upper())  # type: ignore[assignment]
                if rate is None:
                    findings.append(self._finding(
                        RATE_REQUIRED, "blocker",
                        f"no {member_ledger.base_currency} → {group_currency} rate was "
                        f"supplied for {member_ledger.name!r}",
                    ))
                    member_rows.append({"ledgerId": member_ledger.id,
                                        "name": member_ledger.name,
                                        "currency": member_ledger.base_currency,
                                        "ownershipPct": f"{pct * 100:f}",
                                        "included": False, "reason": "RATE_REQUIRED"})
                    continue

            accounts = self.ledger.store.list_accounts(member_ledger.id)
            for account in accounts:
                existing = accounts_by_code.get(account.code)
                if existing is not None and existing.type != account.type:
                    findings.append(self._finding(
                        ACCOUNT_TYPE_CONFLICT, "blocker",
                        f"account {account.code} is {existing.type} in "
                        f"{accounts_by_code[account.code].ledger_id[:12]}… and "
                        f"{account.type} in {member_ledger.name!r}",
                    ))
                else:
                    accounts_by_code.setdefault(account.code, account)

            cumulative = self.ledger.store.postings(member_ledger.id,
                                                    end=when.isoformat())
            period = (self.ledger.store.postings(member_ledger.id, start=start_iso,
                                                 end=when.isoformat())
                      if start_iso else cumulative)
            scale = pct * rate
            for row in cumulative:
                code = str(row["accountCode"])
                net = (row["baseDebit"] or ZERO) - (row["baseCredit"] or ZERO)
                totals[code] = totals.get(code, ZERO) + q_money(net * scale)
            for row in period:
                code = str(row["accountCode"])
                net = (row["baseDebit"] or ZERO) - (row["baseCredit"] or ZERO)
                period_totals[code] = period_totals.get(code, ZERO) + q_money(net * scale)
            member_rows.append({
                "ledgerId": member_ledger.id,
                "name": member_ledger.name,
                "currency": member_ledger.base_currency,
                "ownershipPct": f"{q_money(pct * Decimal(100)):f}",
                "rate": f"{rate:f}",
                "included": True,
                "entryCount": self.ledger.store.count_entries(member_ledger.id,
                                                              end=when.isoformat()),
            })

        if not any(row.get("included") for row in member_rows):
            return self._blocked(group, when, member_rows, findings,
                                 accounts_by_code, totals)

        bs_elim = self._eliminate(totals, accounts_by_code, *BS_PAIR,
                                  kind="BALANCE_SHEET", findings=findings)
        pl_elim = self._eliminate(period_totals, accounts_by_code, *PL_PAIR,
                                  kind="PROFIT_AND_LOSS", findings=findings)

        consolidated: dict[str, Decimal] = dict(totals)
        for elimination in (bs_elim, pl_elim):
            for code, amount in elimination.debit_accounts:
                consolidated[code] = consolidated.get(code, ZERO) + amount
            for code, amount in elimination.credit_accounts:
                consolidated[code] = consolidated.get(code, ZERO) - amount

        accounts = sorted(accounts_by_code.values(), key=lambda account: account.code)
        bs_postings = self._postings(consolidated)
        pl_source = dict(period_totals)
        for code, amount in pl_elim.debit_accounts:
            pl_source[code] = pl_source.get(code, ZERO) + amount
        for code, amount in pl_elim.credit_accounts:
            pl_source[code] = pl_source.get(code, ZERO) - amount
        pl_postings = self._postings(pl_source)

        sheet = stmts.balance_sheet(accounts, bs_postings, as_of=when.isoformat())
        pnl = stmts.income_statement(accounts, pl_postings,
                                     start=start_iso or "", end=when.isoformat())

        checks = list(sheet["checks"]) + [
            {
                "name": "consolidated-balances",
                "ok": sum(consolidated.values(), ZERO) == ZERO,
                "detail": f"sum of every consolidated net is "
                          f"{q_money(sum(consolidated.values(), ZERO)):f}",
            },
            {
                "name": "intercompany-eliminations-balanced",
                "ok": all(e.to_dict()["balanced"] for e in (bs_elim, pl_elim)),
                "detail": "every elimination posts a debit and an equal credit",
            },
        ]
        if bs_elim.unmatched != ZERO or pl_elim.unmatched != ZERO:
            findings.append(self._finding(
                "INTERCOMPANY_OUT_OF_BALANCE", "warning",
                f"{q_money(bs_elim.unmatched):f} of intercompany balance-sheet "
                f"balance and {q_money(pl_elim.unmatched):f} of intercompany P&L "
                "could not be matched; the remainder stays in the consolidated books",
            ))

        status = "BLOCKED" if any(f["severity"] == "blocker" for f in findings) else "CONSOLIDATED"
        payload = {
            "groupId": group["id"],
            "groupName": group["name"],
            "asOf": when.isoformat(),
            "startDate": start_iso,
            "groupCurrency": group_currency,
            "ownershipMethod": "PROPORTIONATE",
            "members": member_rows,
            "totals": [
                {
                    "code": account.code,
                    "name": account.name,
                    "type": account.type,
                    "subtype": account.subtype,
                    "net": f"{q_money(consolidated.get(account.code, ZERO)):f}",
                }
                for account in accounts
                if consolidated.get(account.code, ZERO) != ZERO
            ],
            "eliminations": [bs_elim.to_dict(), pl_elim.to_dict()],
            "balanceSheet": sheet,
            "incomeStatement": pnl,
            "checks": checks,
            "findings": findings,
            "status": status,
        }
        included = [row["ledgerId"] for row in member_rows if row.get("included")]
        if included:
            self.ledger.store.audit(included[0], "GROUP_CONSOLIDATED",
                                    subject_id=group["id"], actor=actor_id,
                                    detail={"groupId": group["id"],
                                            "asOf": when.isoformat(),
                                            "status": status,
                                            "members": len(included)})
        return payload

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _postings(totals: dict[str, Decimal]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for code, net in totals.items():
            if net > ZERO:
                rows.append({"accountCode": code, "baseDebit": net, "baseCredit": ZERO})
            elif net < ZERO:
                rows.append({"accountCode": code, "baseDebit": ZERO, "baseCredit": -net})
        return rows

    def _eliminate(self, totals: dict[str, Decimal],
                   accounts_by_code: dict[str, Account],
                   debit_subtype: str, credit_subtype: str, *, kind: str,
                   findings: list[dict[str, Any]]) -> Elimination:
        debit_accounts = sorted(
            (code, amount) for code, amount in totals.items()
            if amount > ZERO and code in accounts_by_code
            and accounts_by_code[code].subtype == debit_subtype
        )
        credit_accounts = sorted(
            (code, -amount) for code, amount in totals.items()
            if amount < ZERO and code in accounts_by_code
            and accounts_by_code[code].subtype == credit_subtype
        )
        debit_total = sum((amount for _, amount in debit_accounts), ZERO)
        credit_total = sum((amount for _, amount in credit_accounts), ZERO)
        matched = min(debit_total, credit_total)
        if matched <= ZERO:
            return Elimination(kind, ZERO, [], [], ZERO,
                               q_money(abs(debit_total - credit_total)))
        debit_leg = self._allocate(matched, debit_accounts)
        credit_leg = self._allocate(matched, credit_accounts)
        return Elimination(
            kind=kind,
            amount=matched,
            # An elimination REDUCES both balances: it debits the credit-side
            # account and credits the debit-side account (Dr payable / Cr
            # receivable; Dr revenue / Cr expense).
            debit_accounts=[(code, amount) for code, amount in credit_leg],
            credit_accounts=[(code, amount) for code, amount in debit_leg],
            matched=matched,
            unmatched=q_money(abs(debit_total - credit_total)),
        )

    @staticmethod
    def _allocate(target: Decimal, balances: Sequence[tuple[str, Decimal]]) -> list[tuple[str, Decimal]]:
        """Split `target` across balances, with the last one taking the remainder."""
        out: list[tuple[str, Decimal]] = []
        remaining = target
        for index, (code, balance) in enumerate(balances):
            if remaining <= ZERO:
                break
            if index == len(balances) - 1:
                amount = q_money(remaining)
            else:
                amount = q_money(min(balance, remaining))
            if amount > ZERO:
                out.append((code, amount))
                remaining = q_money(remaining - amount)
        return out

    def _blocked(self, group: dict[str, Any], when: date,
                 member_rows: list[dict[str, Any]], findings: list[dict[str, Any]],
                 accounts_by_code: dict[str, Account],
                 totals: dict[str, Decimal]) -> dict[str, Any]:
        return {
            "groupId": group["id"],
            "groupName": group["name"],
            "asOf": when.isoformat(),
            "groupCurrency": group["baseCurrency"].upper(),
            "ownershipMethod": "PROPORTIONATE",
            "members": member_rows,
            "totals": [],
            "eliminations": [],
            "balanceSheet": None,
            "incomeStatement": None,
            "checks": [],
            "findings": findings,
            "status": "BLOCKED",
        }

    @staticmethod
    def _finding(code: str, severity: str, detail: str) -> dict[str, Any]:
        return {"code": code, "severity": severity, "detail": detail}


__all__ = ["ConsolidationService", "Elimination"]
