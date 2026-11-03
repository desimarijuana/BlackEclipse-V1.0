"""The period close: a deterministic checklist, then a decision.

A close is not "there are no errors". It is: the books balance, nothing is parked
in suspense, the cash accounts agree with their statements, the schedules have run,
no foreign balance is left at a stale rate, and nothing is duplicated. Each check
returns a finding with a severity:

  * **blocker** — the period must not close (an unbalanced trial balance, a
    suspense balance). `close_period` refuses while one stands.
  * **warning** — the period may close, but the operator should look (negative
    cash, a missing reconciliation, a schedule still due, a possible duplicate, a
    foreign balance never revalued).

Findings are facts, not opinions: every one names the account or entry it is about.
A close run is persisted, so "we closed March" is a record with the evidence that
was true at the time.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from . import statements as stmts
from .errors import CLOSE_RUN_NOT_FOUND, LedgerError
from .money import ZERO, q_money
from .schedules import due_entries


def _run_id() -> str:
    return f"cls_{uuid.uuid4().hex[:20]}"


def _finding(code: str, severity: str, detail: str, *,
             account_code: Optional[str] = None,
             entry_id: Optional[str] = None,
             amount: Optional[Decimal] = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "severity": severity, "detail": detail}
    if account_code:
        payload["accountCode"] = account_code
    if entry_id:
        payload["entryId"] = entry_id
    if amount is not None:
        payload["amount"] = f"{q_money(amount):f}"
    return payload


def evaluate(
    service: Any,
    ledger_id: str,
    *,
    start: str,
    end: str,
    actor_id: Optional[str] = None,
) -> dict[str, Any]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    ledger = service.store.get_ledger(ledger_id)
    assert ledger is not None
    accounts = service.store.list_accounts(ledger_id)
    accounts_by_code = {account.code: account for account in accounts}

    start_iso = str(start)[:10]
    end_iso = str(end)[:10]
    before = service.store.postings(
        ledger_id, end=(date.fromisoformat(start_iso) - timedelta(days=1)).isoformat()
    )
    period = service.store.postings(ledger_id, start=start_iso, end=end_iso)

    findings: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    # 1) Nothing parked in suspense.
    suspense_net = ZERO
    for entry in stmts.build_balances(accounts, before, period).values():
        if entry.account.subtype == "SUSPENSE":
            suspense_net += entry.net
    checks.append({
        "name": "suspense-is-clear",
        "ok": suspense_net == ZERO,
        "detail": f"suspense balance {q_money(suspense_net):f}",
    })
    if suspense_net != ZERO:
        findings.append(_finding(
            "SUSPENSE_BALANCE", "blocker",
            f"suspense carries {q_money(suspense_net):f}; categorise those rows first",
            amount=suspense_net,
        ))

    # 2) The trial balance must balance for the period.
    trial = stmts.trial_balance(accounts, before, period, start=start_iso, end=end_iso)
    checks.append({
        "name": "trial-balance-balanced",
        "ok": trial["balanced"],
        "detail": f"debits {trial['totals']['debit']} vs credits {trial['totals']['credit']}",
    })
    for check in trial["checks"]:
        if not check["ok"]:
            findings.append(_finding(
                "TRIAL_BALANCE_BROKEN", "blocker",
                f"{check['name']}: {check['detail']}",
            ))

    # 3) There is something to close.
    entry_count = service.store.count_entries(ledger_id, start=start_iso, end=end_iso)
    checks.append({
        "name": "period-has-entries",
        "ok": entry_count > 0,
        "detail": f"{entry_count} journal entr{'y' if entry_count == 1 else 'ies'}",
    })
    if entry_count == 0:
        findings.append(_finding(
            "NO_ENTRIES", "warning",
            "the period has no journal entries; closing an empty period is allowed "
            "but usually means something was not posted",
        ))

    # 4) Import batches that did not finish.
    for batch in service.store.list_import_batches(ledger_id, limit=100):
        if batch["status"] in ("PARTIAL", "FAILED") and \
                start_iso <= str(batch["createdAt"])[:10] <= end_iso:
            findings.append(_finding(
                "IMPORT_INCOMPLETE", "warning",
                f"import {batch['id']} is {batch['status']} "
                f"({batch['errorCount']} row error(s), {batch['accountCode']})",
                account_code=batch["accountCode"],
            ))

    # 5) Cash accounts: no unexplained overdraft, and reconcile the ones that moved.
    cumulative = stmts.build_balances(accounts, (), before + period)
    cash_accounts = [account for account in accounts if account.is_cash]
    moved: set[str] = {str(row["accountCode"]) for row in period}
    for account in cash_accounts:
        entry = cumulative.get(account.code)
        if entry is None or entry.net == ZERO:
            continue
        checks.append({
            "name": f"cash-non-negative:{account.code}",
            "ok": entry.net > ZERO,
            "detail": f"{q_money(entry.net):f}",
        })
        if entry.net < ZERO:
            findings.append(_finding(
                "NEGATIVE_CASH", "warning",
                f"cash account {account.code} has a credit balance "
                f"{q_money(-entry.net):f} at {end_iso} (an overdraft, or a missing receipt)",
                account_code=account.code, amount=entry.net,
            ))
        if account.code not in moved:
            continue
        run = _latest_reconciliation(service, ledger_id, account.code)
        current = (
            run is not None
            and run["status"] == "RECONCILED"
            and str(run.get("endDate") or "") >= end_iso
        )
        checks.append({
            "name": f"cash-reconciled:{account.code}",
            "ok": current,
            "detail": "no current reconciled statement" if not current else
            f"reconciled {run['startDate']}..{run['endDate']}",
        })
        if not current:
            findings.append(_finding(
                "RECONCILIATION_NOT_CURRENT", "warning",
                f"cash account {account.code} moved in this period but has no "
                f"RECONCILED run covering {end_iso}",
                account_code=account.code,
            ))

    # 6) Schedules that should have run by the period end.
    for schedule in service.store.list_schedules(ledger_id, active_only=True):
        due = due_entries(schedule, end_iso)
        if not due:
            continue
        findings.append(_finding(
            "SCHEDULE_DUE", "warning",
            f"schedule {schedule.name!r} ({schedule.kind}) has {len(due)} unposted "
            f"period(s) due by {end_iso}",
        ))
    checks.append({
        "name": "schedules-current",
        "ok": not any(f["code"] == "SCHEDULE_DUE" for f in findings),
        "detail": "",
    })

    # 7) Foreign monetary balances left at a stale rate.
    base_currency = ledger.base_currency.upper()
    period_by_account: dict[str, list[dict[str, Any]]] = {}
    for row in period:
        period_by_account.setdefault(str(row["accountCode"]), []).append(row)
    for account in accounts:
        if account.type not in ("ASSET", "LIABILITY") or not account.active:
            continue
        if not account.currency or account.currency.upper() == base_currency:
            continue
        entry = cumulative.get(account.code)
        if entry is None or entry.net == ZERO:
            continue
        revalued = any(
            str(row.get("externalId") or "").startswith(f"fxrev:{account.code}:")
            for row in period_by_account.get(account.code, [])
        )
        if not revalued:
            findings.append(_finding(
                "FX_REVALUATION_MISSING", "warning",
                f"{account.currency} account {account.code} carries "
                f"{q_money(entry.net):f} {base_currency} and was not revalued in this period",
                account_code=account.code, amount=entry.net,
            ))
    checks.append({
        "name": "fx-revalued",
        "ok": not any(f["code"] == "FX_REVALUATION_MISSING" for f in findings),
        "detail": "",
    })

    # 8) Obvious duplicates: same day, same total, same non-empty memo.
    seen: dict[tuple[str, str, str], str] = {}
    for entry in service.store.list_entries(ledger_id, start=start_iso, end=end_iso,
                                            limit=1000):
        if not entry.memo:
            continue
        key = (entry.entry_date, f"{q_money(sum((line.base_debit for line in entry.lines), ZERO)):f}",
               entry.memo.strip().casefold())
        if key in seen and entry.status == "POSTED":
            findings.append(_finding(
                "POSSIBLE_DUPLICATE", "warning",
                f"entry #{entry.entry_no} repeats entry {seen[key]} "
                f"({entry.entry_date}, {key[1]}, same memo)",
                entry_id=entry.id,
            ))
        else:
            seen[key] = f"#{entry.entry_no}"

    blockers = [finding for finding in findings if finding["severity"] == "blocker"]
    warnings = [finding for finding in findings if finding["severity"] == "warning"]
    return {
        "ledgerId": ledger_id,
        "startDate": start_iso,
        "endDate": end_iso,
        "status": "BLOCKED" if blockers else "READY",
        "blockerCount": len(blockers),
        "warningCount": len(warnings),
        "entryCount": entry_count,
        "findings": findings,
        "checks": checks,
    }


def _latest_reconciliation(service: Any, ledger_id: str,
                           account_code: str) -> Optional[dict[str, Any]]:
    for run in service.store.list_reconciliations(ledger_id, limit=200):
        if run["accountCode"] == account_code:
            return run
    return None


def persist(service: Any, report: dict[str, Any], *,
            period_id: Optional[str] = None,
            actor_id: Optional[str] = None) -> dict[str, Any]:
    run_id = _run_id()
    record = service.store.insert_close_run({
        "id": run_id,
        "ledgerId": report["ledgerId"],
        "periodId": period_id,
        "startDate": report["startDate"],
        "endDate": report["endDate"],
        "status": report["status"],
        "blockerCount": report["blockerCount"],
        "warningCount": report["warningCount"],
        "createdBy": actor_id,
        "detail": {
            "entryCount": report["entryCount"],
            "findings": report["findings"],
            "checks": report["checks"],
        },
    })
    service.store.audit(
        report["ledgerId"], "CLOSE_EVALUATED", subject_id=run_id, actor=actor_id,
        detail={"status": report["status"],
                "blockers": report["blockerCount"],
                "warnings": report["warningCount"]},
    )
    return record


def list_runs(service: Any, ledger_id: str, *, limit: int = 50,
              actor_id: Optional[str] = None) -> list[dict[str, Any]]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    return service.store.list_close_runs(ledger_id, limit=limit)


def get_run(service: Any, ledger_id: str, run_id: str, *,
            actor_id: Optional[str] = None) -> dict[str, Any]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    record = service.store.get_close_run(str(run_id))
    if record is None or record["ledgerId"] != ledger_id:
        raise LedgerError(CLOSE_RUN_NOT_FOUND, f"close run {run_id} not found",
                          {"runId": str(run_id)})
    return record


__all__ = ["evaluate", "get_run", "list_runs", "persist"]
