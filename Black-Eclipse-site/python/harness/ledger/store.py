"""Ledger persistence on the ONE `agent-memory.db` connection.

Same reasoning as the Portfolio Accounting Engine: `jdds.db` is the committed
market-data vault; a company's books are private user/agent state and must never
be committed or treated as market data. The runtime already owns durable state in
`agent-memory.db` through the shared `AgentMemoryStore`, so the ledger adds NO
second database and NO migration step — just idempotent DDL.

Money is stored as exact decimal STRINGS. A balance read out of SQLite is parsed
back into `Decimal`; it is never a float.

Append-only: there is no UPDATE path for a posted entry or its lines. The only
mutations are (a) insert a balanced entry + its lines in one transaction,
(b) stamp `reversedByEntryId` on the original so the reversal is traceable, and
(c) move a period's status. That is the whole write surface.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable, Optional, Sequence

from ..persistence import now_iso
from .errors import DATABASE_FAILURE, DUPLICATE_ENTRY, ENTRY_NOT_FOUND, LedgerError
from .models import Account, JournalEntry, JournalLine, Ledger, Period
from .money import D, ZERO

_SCHEMA = """
CREATE TABLE IF NOT EXISTS Ledger (
  id                    TEXT PRIMARY KEY,
  name                  TEXT NOT NULL,
  baseCurrency          TEXT NOT NULL DEFAULT 'USD',
  ownerId               TEXT,
  fiscalYearStartMonth  INTEGER NOT NULL DEFAULT 1,
  chartTemplate         TEXT NOT NULL DEFAULT 'standard',
  status                TEXT NOT NULL DEFAULT 'ACTIVE',
  metadata              TEXT NOT NULL DEFAULT '{}',
  createdAt             TEXT NOT NULL,
  updatedAt             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_owner ON Ledger(ownerId);

CREATE TABLE IF NOT EXISTS LedgerAccount (
  id                TEXT PRIMARY KEY,
  ledgerId          TEXT NOT NULL,
  code              TEXT NOT NULL,
  name              TEXT NOT NULL,
  type              TEXT NOT NULL,
  subtype           TEXT NOT NULL DEFAULT '',
  normalBalance     TEXT NOT NULL,
  parentCode        TEXT,
  currency          TEXT NOT NULL DEFAULT '',
  cashFlowCategory  TEXT NOT NULL DEFAULT '',
  isCash            INTEGER NOT NULL DEFAULT 0,
  isContra          INTEGER NOT NULL DEFAULT 0,
  active            INTEGER NOT NULL DEFAULT 1,
  createdAt         TEXT NOT NULL,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_account_code
  ON LedgerAccount(ledgerId, code);
CREATE INDEX IF NOT EXISTS idx_ledger_account_type ON LedgerAccount(ledgerId, type);

CREATE TABLE IF NOT EXISTS LedgerPeriod (
  id          TEXT PRIMARY KEY,
  ledgerId    TEXT NOT NULL,
  fiscalYear  INTEGER NOT NULL,
  periodNo    INTEGER NOT NULL,
  startDate   TEXT NOT NULL,
  endDate     TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'OPEN',
  closedAt    TEXT,
  closedBy    TEXT,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_period
  ON LedgerPeriod(ledgerId, fiscalYear, periodNo);

CREATE TABLE IF NOT EXISTS JournalEntry (
  id                 TEXT PRIMARY KEY,
  ledgerId           TEXT NOT NULL,
  entryNo            INTEGER NOT NULL,
  entryDate          TEXT NOT NULL,
  periodId           TEXT NOT NULL,
  memo               TEXT NOT NULL DEFAULT '',
  source             TEXT NOT NULL DEFAULT 'manual',
  externalId         TEXT,
  status             TEXT NOT NULL DEFAULT 'POSTED',
  reversesEntryId    TEXT,
  reversedByEntryId  TEXT,
  createdBy          TEXT,
  createdAt          TEXT NOT NULL,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_journal_entry_no ON JournalEntry(ledgerId, entryNo);
CREATE INDEX IF NOT EXISTS idx_journal_entry_date ON JournalEntry(ledgerId, entryDate);
CREATE UNIQUE INDEX IF NOT EXISTS uq_journal_entry_dedupe
  ON JournalEntry(ledgerId, source, externalId)
  WHERE externalId IS NOT NULL;

CREATE TABLE IF NOT EXISTS JournalLine (
  id           TEXT PRIMARY KEY,
  ledgerId     TEXT NOT NULL,
  entryId      TEXT NOT NULL,
  lineNo       INTEGER NOT NULL,
  accountCode  TEXT NOT NULL,
  accountId    TEXT NOT NULL,
  debit        TEXT NOT NULL DEFAULT '0',
  credit       TEXT NOT NULL DEFAULT '0',
  baseDebit    TEXT NOT NULL DEFAULT '0',
  baseCredit   TEXT NOT NULL DEFAULT '0',
  currency     TEXT NOT NULL DEFAULT 'USD',
  fxRate       TEXT,
  memo         TEXT,
  dimensions   TEXT NOT NULL DEFAULT '{}',
  baseOnly     INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (entryId) REFERENCES JournalEntry(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_journal_line_entry ON JournalLine(entryId);
CREATE INDEX IF NOT EXISTS idx_journal_line_account ON JournalLine(ledgerId, accountCode);

CREATE TABLE IF NOT EXISTS LedgerAuditEvent (
  id         TEXT PRIMARY KEY,
  ledgerId   TEXT NOT NULL,
  kind       TEXT NOT NULL,
  subjectId  TEXT,
  actor      TEXT,
  detail     TEXT NOT NULL DEFAULT '{}',
  createdAt  TEXT NOT NULL,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ledger_audit ON LedgerAuditEvent(ledgerId, createdAt);

CREATE TABLE IF NOT EXISTS LedgerRule (
  id             TEXT PRIMARY KEY,
  ledgerId       TEXT NOT NULL,
  name           TEXT NOT NULL,
  version        INTEGER NOT NULL,
  priority       INTEGER NOT NULL DEFAULT 100,
  matchJson      TEXT NOT NULL,
  targetAccount  TEXT NOT NULL,
  active         INTEGER NOT NULL DEFAULT 1,
  createdBy      TEXT,
  createdAt      TEXT NOT NULL,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_rule_version ON LedgerRule(ledgerId, name, version);
CREATE INDEX IF NOT EXISTS idx_ledger_rule_active ON LedgerRule(ledgerId, active);

CREATE TABLE IF NOT EXISTS LedgerImportBatch (
  id              TEXT PRIMARY KEY,
  ledgerId        TEXT NOT NULL,
  accountCode     TEXT NOT NULL,
  source          TEXT NOT NULL DEFAULT 'import',
  format          TEXT NOT NULL,
  batchRef        TEXT,
  rowCount        INTEGER NOT NULL DEFAULT 0,
  postedCount     INTEGER NOT NULL DEFAULT 0,
  duplicateCount  INTEGER NOT NULL DEFAULT 0,
  errorCount      INTEGER NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'COMPLETE',
  detail          TEXT NOT NULL DEFAULT '{}',
  createdBy       TEXT,
  createdAt       TEXT NOT NULL,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ledger_import ON LedgerImportBatch(ledgerId, createdAt);

CREATE TABLE IF NOT EXISTS LedgerReconciliation (
  id                TEXT PRIMARY KEY,
  ledgerId          TEXT NOT NULL,
  accountCode       TEXT NOT NULL,
  startDate         TEXT,
  endDate           TEXT,
  statementBalance  TEXT,
  openingBalance    TEXT,
  closingBalance    TEXT,
  difference        TEXT,
  tolerance         TEXT NOT NULL DEFAULT '0.01000000',
  matchedCount      INTEGER NOT NULL DEFAULT 0,
  mismatchCount     INTEGER NOT NULL DEFAULT 0,
  missingCount      INTEGER NOT NULL DEFAULT 0,
  unknownCount      INTEGER NOT NULL DEFAULT 0,
  status            TEXT NOT NULL DEFAULT 'UNKNOWN',
  detail            TEXT NOT NULL DEFAULT '{}',
  createdBy         TEXT,
  createdAt         TEXT NOT NULL,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ledger_recon ON LedgerReconciliation(ledgerId, createdAt);

CREATE TABLE IF NOT EXISTS LedgerReconciliationItem (
  id                TEXT PRIMARY KEY,
  reconciliationId  TEXT NOT NULL,
  ledgerId          TEXT NOT NULL,
  rowNo             INTEGER,
  entryDate         TEXT,
  description       TEXT,
  amount            TEXT,
  status            TEXT NOT NULL,
  method            TEXT,
  entryId           TEXT,
  detail            TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (reconciliationId) REFERENCES LedgerReconciliation(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ledger_recon_item
  ON LedgerReconciliationItem(reconciliationId);

CREATE TABLE IF NOT EXISTS LedgerSchedule (
  id              TEXT PRIMARY KEY,
  ledgerId        TEXT NOT NULL,
  kind            TEXT NOT NULL,
  name            TEXT NOT NULL,
  method          TEXT NOT NULL,
  startDate       TEXT NOT NULL,
  periods         INTEGER NOT NULL,
  cost            TEXT NOT NULL,
  salvage         TEXT NOT NULL DEFAULT '0',
  expenseAccount  TEXT NOT NULL,
  contraAccount   TEXT NOT NULL,
  currency        TEXT NOT NULL DEFAULT 'USD',
  factor          TEXT NOT NULL DEFAULT '2',
  status          TEXT NOT NULL DEFAULT 'ACTIVE',
  postedThrough   INTEGER NOT NULL DEFAULT 0,
  createdBy       TEXT,
  createdAt       TEXT NOT NULL,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ledger_schedule ON LedgerSchedule(ledgerId, createdAt);

CREATE TABLE IF NOT EXISTS LedgerCloseRun (
  id            TEXT PRIMARY KEY,
  ledgerId      TEXT NOT NULL,
  periodId      TEXT,
  startDate     TEXT,
  endDate       TEXT,
  status        TEXT NOT NULL,
  blockerCount  INTEGER NOT NULL DEFAULT 0,
  warningCount  INTEGER NOT NULL DEFAULT 0,
  detail        TEXT NOT NULL DEFAULT '{}',
  createdBy     TEXT,
  createdAt     TEXT NOT NULL,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ledger_close ON LedgerCloseRun(ledgerId, createdAt);
"""


def _loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _dec(value: Any) -> Any:
    return D(value) if value not in (None, "") else ZERO


def _account_row(row: Any) -> Account:
    return Account(
        id=row["id"],
        ledger_id=row["ledgerId"],
        code=row["code"],
        name=row["name"],
        type=row["type"],
        subtype=row["subtype"] or "",
        normal_balance=row["normalBalance"],
        parent_code=row["parentCode"],
        currency=row["currency"] or "",
        cash_flow_category=row["cashFlowCategory"] or "",
        is_cash=bool(row["isCash"]),
        is_contra=bool(row["isContra"]),
        active=bool(row["active"]),
        created_at=row["createdAt"],
    )


def _ledger_row(row: Any) -> Ledger:
    return Ledger(
        id=row["id"],
        name=row["name"],
        base_currency=row["baseCurrency"],
        owner_id=row["ownerId"],
        fiscal_year_start_month=int(row["fiscalYearStartMonth"]),
        chart_template=row["chartTemplate"],
        status=row["status"],
        metadata=_loads(row["metadata"], {}),
        created_at=row["createdAt"],
        updated_at=row["updatedAt"],
    )


def _period_row(row: Any) -> Period:
    return Period(
        id=row["id"],
        ledger_id=row["ledgerId"],
        fiscal_year=int(row["fiscalYear"]),
        period_no=int(row["periodNo"]),
        start_date=row["startDate"],
        end_date=row["endDate"],
        status=row["status"],
        closed_at=row["closedAt"],
        closed_by=row["closedBy"],
    )


def _line_row(row: Any) -> JournalLine:
    return JournalLine(
        id=row["id"],
        entry_id=row["entryId"],
        line_no=int(row["lineNo"]),
        account_code=row["accountCode"],
        account_id=row["accountId"],
        debit=_dec(row["debit"]),
        credit=_dec(row["credit"]),
        base_debit=_dec(row["baseDebit"]),
        base_credit=_dec(row["baseCredit"]),
        currency=row["currency"],
        fx_rate=D(row["fxRate"]) if row["fxRate"] not in (None, "") else None,
        memo=row["memo"],
        dimensions=_loads(row["dimensions"], {}),
        base_only=bool(row["baseOnly"]) if "baseOnly" in row.keys() else False,
    )


def _entry_row(row: Any, lines: Sequence[JournalLine]) -> JournalEntry:
    return JournalEntry(
        id=row["id"],
        ledger_id=row["ledgerId"],
        entry_no=int(row["entryNo"]),
        entry_date=row["entryDate"],
        period_id=row["periodId"],
        memo=row["memo"] or "",
        source=row["source"] or "manual",
        external_id=row["externalId"],
        status=row["status"],
        reverses_entry_id=row["reversesEntryId"],
        reversed_by_entry_id=row["reversedByEntryId"],
        created_by=row["createdBy"],
        created_at=row["createdAt"],
        lines=list(lines),
    )


class LedgerStore:
    """CRUD over the ledger tables on the shared agent-memory connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self) -> sqlite3.Connection:
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        self._add_missing_columns()
        self._db.commit()

    def _add_missing_columns(self) -> None:
        """Additive, non-destructive migration for a DB created before a column.

        `CREATE TABLE IF NOT EXISTS` never alters an existing table, so a column
        added after the first release must be ALTER-ed in. Only adds; never drops
        or rewrites data.
        """
        wanted = {"JournalLine": {"baseOnly": "INTEGER NOT NULL DEFAULT 0"}}
        for table, columns in wanted.items():
            existing = {row["name"] for row in
                        self._db.execute(f"PRAGMA table_info({table})").fetchall()}
            for column, decl in columns.items():
                if column not in existing:
                    self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    # ── Ledgers ──────────────────────────────────────────────────────────────
    def create_ledger(
        self,
        ledger_id: str,
        name: str,
        *,
        base_currency: str = "USD",
        owner_id: Optional[str] = None,
        fiscal_year_start_month: int = 1,
        chart_template: str = "standard",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Ledger:
        now = now_iso()
        self._db.execute(
            """INSERT INTO Ledger
               (id, name, baseCurrency, ownerId, fiscalYearStartMonth, chartTemplate,
                status, metadata, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)""",
            (ledger_id, name, base_currency, owner_id, int(fiscal_year_start_month),
             chart_template, _dumps(metadata), now, now),
        )
        self._db.commit()
        return Ledger(
            id=ledger_id, name=name, base_currency=base_currency, owner_id=owner_id,
            fiscal_year_start_month=int(fiscal_year_start_month),
            chart_template=chart_template, metadata=dict(metadata or {}),
            created_at=now, updated_at=now,
        )

    def get_ledger(self, ledger_id: str) -> Optional[Ledger]:
        row = self._db.execute("SELECT * FROM Ledger WHERE id=?", (ledger_id,)).fetchone()
        return _ledger_row(row) if row else None

    def list_ledgers(self, owner_id: Optional[str] = None) -> list[dict[str, Any]]:
        if owner_id:
            rows = self._db.execute(
                "SELECT * FROM Ledger WHERE ownerId=? OR ownerId IS NULL ORDER BY createdAt DESC",
                (owner_id,),
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM Ledger ORDER BY createdAt DESC").fetchall()
        return [_ledger_row(row).to_dict() for row in rows]

    def delete_ledger(self, ledger_id: str) -> bool:
        """Delete a book and everything under it. Explicit, so it never relies
        on `PRAGMA foreign_keys` being enabled."""
        exists = self._db.execute("SELECT 1 FROM Ledger WHERE id=?", (ledger_id,)).fetchone()
        if not exists:
            return False
        self._db.execute(
            "DELETE FROM JournalLine WHERE ledgerId=?", (ledger_id,)
        )
        self._db.execute(
            "DELETE FROM JournalEntry WHERE ledgerId=?", (ledger_id,)
        )
        self._db.execute("DELETE FROM LedgerAuditEvent WHERE ledgerId=?", (ledger_id,))
        self._db.execute("DELETE FROM LedgerReconciliationItem WHERE ledgerId=?", (ledger_id,))
        self._db.execute("DELETE FROM LedgerReconciliation WHERE ledgerId=?", (ledger_id,))
        self._db.execute("DELETE FROM LedgerImportBatch WHERE ledgerId=?", (ledger_id,))
        self._db.execute("DELETE FROM LedgerRule WHERE ledgerId=?", (ledger_id,))
        self._db.execute("DELETE FROM LedgerSchedule WHERE ledgerId=?", (ledger_id,))
        self._db.execute("DELETE FROM LedgerCloseRun WHERE ledgerId=?", (ledger_id,))
        self._db.execute("DELETE FROM LedgerAccount WHERE ledgerId=?", (ledger_id,))
        self._db.execute("DELETE FROM LedgerPeriod WHERE ledgerId=?", (ledger_id,))
        self._db.execute("DELETE FROM Ledger WHERE id=?", (ledger_id,))
        self._db.commit()
        return True

    def touch_ledger(self, ledger_id: str) -> None:
        self._db.execute("UPDATE Ledger SET updatedAt=? WHERE id=?", (now_iso(), ledger_id))
        self._db.commit()

    # ── Accounts ─────────────────────────────────────────────────────────────
    def insert_accounts(self, accounts: Iterable[Account]) -> int:
        count = 0
        for account in accounts:
            self._db.execute(
                """INSERT INTO LedgerAccount
                   (id, ledgerId, code, name, type, subtype, normalBalance, parentCode,
                    currency, cashFlowCategory, isCash, isContra, active, createdAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    account.id, account.ledger_id, account.code, account.name, account.type,
                    account.subtype, account.normal_balance, account.parent_code, account.currency,
                    account.cash_flow_category, int(account.is_cash), int(account.is_contra),
                    int(account.active), account.created_at or now_iso(),
                ),
            )
            count += 1
        self._db.commit()
        return count

    def add_account(self, account: Account) -> Account:
        self.insert_accounts([account])
        return account

    def get_account(self, ledger_id: str, code: str) -> Optional[Account]:
        row = self._db.execute(
            "SELECT * FROM LedgerAccount WHERE ledgerId=? AND code=?", (ledger_id, code)
        ).fetchone()
        return _account_row(row) if row else None

    def list_accounts(self, ledger_id: str, *, include_inactive: bool = True) -> list[Account]:
        sql = "SELECT * FROM LedgerAccount WHERE ledgerId=?"
        if not include_inactive:
            sql += " AND active=1"
        sql += " ORDER BY code"
        return [_account_row(row) for row in self._db.execute(sql, (ledger_id,)).fetchall()]

    def set_account_active(self, ledger_id: str, code: str, active: bool) -> bool:
        cursor = self._db.execute(
            "UPDATE LedgerAccount SET active=? WHERE ledgerId=? AND code=?",
            (int(bool(active)), ledger_id, code),
        )
        self._db.commit()
        return cursor.rowcount > 0

    def count_accounts(self, ledger_id: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) AS n FROM LedgerAccount WHERE ledgerId=?", (ledger_id,)
        ).fetchone()
        return int(row["n"]) if row else 0

    # ── Periods ──────────────────────────────────────────────────────────────
    def get_period(self, ledger_id: str, fiscal_year: int, period_no: int) -> Optional[Period]:
        row = self._db.execute(
            "SELECT * FROM LedgerPeriod WHERE ledgerId=? AND fiscalYear=? AND periodNo=?",
            (ledger_id, int(fiscal_year), int(period_no)),
        ).fetchone()
        return _period_row(row) if row else None

    def get_period_by_id(self, period_id: str) -> Optional[Period]:
        row = self._db.execute("SELECT * FROM LedgerPeriod WHERE id=?", (period_id,)).fetchone()
        return _period_row(row) if row else None

    def upsert_period(self, period: Period) -> Period:
        self._db.execute(
            """INSERT INTO LedgerPeriod
               (id, ledgerId, fiscalYear, periodNo, startDate, endDate, status, closedAt, closedBy)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 startDate=excluded.startDate, endDate=excluded.endDate""",
            (period.id, period.ledger_id, period.fiscal_year, period.period_no,
             period.start_date, period.end_date, period.status, period.closed_at, period.closed_by),
        )
        self._db.commit()
        return period

    def set_period_status(self, period_id: str, status: str,
                          *, actor: Optional[str] = None) -> Optional[Period]:
        closed_at = now_iso() if status in ("CLOSED", "LOCKED") else None
        self._db.execute(
            "UPDATE LedgerPeriod SET status=?, closedAt=?, closedBy=? WHERE id=?",
            (status, closed_at, actor if status != "OPEN" else None, period_id),
        )
        self._db.commit()
        return self.get_period_by_id(period_id)

    def list_periods(self, ledger_id: str) -> list[Period]:
        rows = self._db.execute(
            "SELECT * FROM LedgerPeriod WHERE ledgerId=? ORDER BY fiscalYear, periodNo",
            (ledger_id,),
        ).fetchall()
        return [_period_row(row) for row in rows]

    # ── Journal ──────────────────────────────────────────────────────────────
    def next_entry_no(self, ledger_id: str) -> int:
        row = self._db.execute(
            "SELECT COALESCE(MAX(entryNo), 0) AS n FROM JournalEntry WHERE ledgerId=?",
            (ledger_id,),
        ).fetchone()
        return int(row["n"] or 0) + 1

    def find_by_external(self, ledger_id: str, source: str,
                         external_id: str) -> Optional[JournalEntry]:
        row = self._db.execute(
            "SELECT * FROM JournalEntry WHERE ledgerId=? AND source=? AND externalId=?",
            (ledger_id, source, external_id),
        ).fetchone()
        if row is None:
            return None
        return self.get_entry(row["id"])

    def insert_entry(self, entry: JournalEntry) -> JournalEntry:
        """Insert an entry and its lines atomically. No update path exists."""
        try:
            self._db.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            # A transaction is already open on this shared connection; the
            # inserts below are still applied atomically at commit.
            pass
        try:
            self._db.execute(
                """INSERT INTO JournalEntry
                   (id, ledgerId, entryNo, entryDate, periodId, memo, source, externalId,
                    status, reversesEntryId, reversedByEntryId, createdBy, createdAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.id, entry.ledger_id, entry.entry_no, entry.entry_date, entry.period_id,
                    entry.memo, entry.source, entry.external_id, entry.status,
                    entry.reverses_entry_id, entry.reversed_by_entry_id, entry.created_by,
                    entry.created_at or now_iso(),
                ),
            )
            for line in entry.lines:
                self._db.execute(
                    """INSERT INTO JournalLine
                       (id, ledgerId, entryId, lineNo, accountCode, accountId, debit, credit,
                        baseDebit, baseCredit, currency, fxRate, memo, dimensions, baseOnly)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        line.id, entry.ledger_id, entry.id, line.line_no, line.account_code,
                        line.account_id, f"{line.debit:f}", f"{line.credit:f}",
                        f"{line.base_debit:f}", f"{line.base_credit:f}", line.currency,
                        None if line.fx_rate is None else f"{line.fx_rate:f}",
                        line.memo, _dumps(line.dimensions), int(bool(line.base_only)),
                    ),
                )
            self._db.commit()
        except sqlite3.IntegrityError as exc:
            self._db.rollback()
            raise LedgerError(
                DUPLICATE_ENTRY,
                f"entry conflicts with an existing posting ({exc})",
                {"ledgerId": entry.ledger_id, "entryNo": entry.entry_no},
            ) from exc
        except sqlite3.Error as exc:  # pragma: no cover - defensive
            self._db.rollback()
            raise LedgerError(DATABASE_FAILURE, f"could not persist the entry: {exc}") from exc
        return entry

    def get_entry(self, entry_id: str, *, include_lines: bool = True) -> Optional[JournalEntry]:
        row = self._db.execute("SELECT * FROM JournalEntry WHERE id=?", (entry_id,)).fetchone()
        if row is None:
            return None
        lines: list[JournalLine] = []
        if include_lines:
            line_rows = self._db.execute(
                "SELECT * FROM JournalLine WHERE entryId=? ORDER BY lineNo", (entry_id,)
            ).fetchall()
            lines = [_line_row(line) for line in line_rows]
        return _entry_row(row, lines)

    def require_entry(self, entry_id: str) -> JournalEntry:
        entry = self.get_entry(entry_id)
        if entry is None:
            raise LedgerError(ENTRY_NOT_FOUND, f"journal entry {entry_id} not found",
                              {"entryId": entry_id})
        return entry

    def mark_reversed(self, entry_id: str, by_entry_id: str) -> None:
        self._db.execute(
            "UPDATE JournalEntry SET status='REVERSED', reversedByEntryId=? WHERE id=?",
            (by_entry_id, entry_id),
        )
        self._db.commit()

    def list_entries(
        self,
        ledger_id: str,
        *,
        start: Optional[str] = None,
        end: Optional[str] = None,
        account_code: Optional[str] = None,
        limit: int = 100,
        include_lines: bool = True,
    ) -> list[JournalEntry]:
        sql = "SELECT DISTINCT e.* FROM JournalEntry e"
        args: list[Any] = []
        if account_code:
            sql += " JOIN JournalLine l ON l.entryId=e.id AND l.accountCode=?"
            args.append(account_code)
        sql += " WHERE e.ledgerId=?"
        args.append(ledger_id)
        if start:
            sql += " AND e.entryDate>=?"
            args.append(start)
        if end:
            sql += " AND e.entryDate<=?"
            args.append(end)
        sql += " ORDER BY e.entryDate DESC, e.entryNo DESC LIMIT ?"
        args.append(max(1, min(int(limit or 100), 5000)))
        rows = self._db.execute(sql, tuple(args)).fetchall()
        out: list[JournalEntry] = []
        for row in rows:
            lines: list[JournalLine] = []
            if include_lines:
                line_rows = self._db.execute(
                    "SELECT * FROM JournalLine WHERE entryId=? ORDER BY lineNo", (row["id"],)
                ).fetchall()
                lines = [_line_row(line) for line in line_rows]
            out.append(_entry_row(row, lines))
        return out

    def count_entries(self, ledger_id: str, *, start: Optional[str] = None,
                      end: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM JournalEntry WHERE ledgerId=?"
        args: list[Any] = [ledger_id]
        if start:
            sql += " AND entryDate>=?"
            args.append(start)
        if end:
            sql += " AND entryDate<=?"
            args.append(end)
        row = self._db.execute(sql, tuple(args)).fetchone()
        return int(row["n"] or 0) if row else 0

    def first_entry_date(self, ledger_id: str) -> Optional[str]:
        row = self._db.execute(
            "SELECT MIN(entryDate) AS d FROM JournalEntry WHERE ledgerId=?", (ledger_id,)
        ).fetchone()
        return row["d"] if row else None

    def postings(
        self,
        ledger_id: str,
        *,
        start: Optional[str] = None,
        end: Optional[str] = None,
        account_code: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Every line in range joined to its entry date, for statement building."""
        sql = (
            "SELECT l.accountCode AS accountCode, l.baseDebit AS baseDebit, "
            "l.baseCredit AS baseCredit, l.debit AS debit, l.credit AS credit, "
            "l.currency AS currency, l.entryId AS entryId, e.entryDate AS entryDate, "
            "e.status AS status, e.externalId AS externalId, e.memo AS memo "
            "FROM JournalLine l JOIN JournalEntry e ON e.id=l.entryId WHERE l.ledgerId=?"
        )
        args: list[Any] = [ledger_id]
        if start:
            sql += " AND e.entryDate>=?"
            args.append(start)
        if end:
            sql += " AND e.entryDate<=?"
            args.append(end)
        if account_code:
            sql += " AND l.accountCode=?"
            args.append(account_code)
        sql += " ORDER BY e.entryDate, l.entryId, l.lineNo"
        rows = self._db.execute(sql, tuple(args)).fetchall()
        return [
            {
                "accountCode": row["accountCode"],
                "baseDebit": _dec(row["baseDebit"]),
                "baseCredit": _dec(row["baseCredit"]),
                "debit": _dec(row["debit"]),
                "credit": _dec(row["credit"]),
                "currency": row["currency"],
                "entryId": row["entryId"],
                "entryDate": row["entryDate"],
                "status": row["status"],
                "externalId": row["externalId"],
                "memo": row["memo"],
            }
            for row in rows
        ]

    # ── Rules (append-only versions) ─────────────────────────────────────────
    def insert_rule(self, rule: Any) -> Any:
        from .rules import CategorisationRule  # noqa: PLC0415 - avoid a cycle

        assert isinstance(rule, CategorisationRule)
        import json as _json

        self._db.execute(
            """INSERT INTO LedgerRule
               (id, ledgerId, name, version, priority, matchJson, targetAccount, active,
                createdBy, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rule.id, rule.ledger_id, rule.name, int(rule.version), int(rule.priority),
             _json.dumps(rule.match.to_dict()), rule.target_account, int(rule.active),
             rule.created_by, rule.created_at or now_iso()),
        )
        self._db.commit()
        return rule

    def _rule_rows(self, sql: str, args: tuple[Any, ...]) -> list[Any]:
        from .rules import CategorisationRule, RuleMatch  # noqa: PLC0415

        out: list[Any] = []
        for row in self._db.execute(sql, args).fetchall():
            match = _loads(row["matchJson"], {})
            out.append(CategorisationRule(
                id=row["id"], ledger_id=row["ledgerId"], name=row["name"],
                version=int(row["version"]), priority=int(row["priority"]),
                match=RuleMatch(
                    payee_contains=tuple(match.get("payeeContains") or ()),
                    payee_regex=match.get("payeeRegex") or "",
                    amount_min=D(match["amountMin"]) if match.get("amountMin") else None,
                    amount_max=D(match["amountMax"]) if match.get("amountMax") else None,
                    direction=match.get("direction") or "ANY",
                ),
                target_account=row["targetAccount"], active=bool(row["active"]),
                created_by=row["createdBy"], created_at=row["createdAt"],
            ))
        return out

    def list_rules(self, ledger_id: str, *, active_only: bool = True) -> list[Any]:
        sql = "SELECT * FROM LedgerRule WHERE ledgerId=?"
        if active_only:
            sql += " AND active=1"
        sql += " ORDER BY priority, name, version"
        return self._rule_rows(sql, (ledger_id,))

    def get_rule(self, rule_id: str) -> Optional[Any]:
        rows = self._rule_rows("SELECT * FROM LedgerRule WHERE id=?", (rule_id,))
        return rows[0] if rows else None

    def latest_rule_version(self, ledger_id: str, name: str) -> int:
        row = self._db.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM LedgerRule WHERE ledgerId=? AND name=?",
            (ledger_id, name),
        ).fetchone()
        return int(row["v"] or 0) if row else 0

    def deactivate_rule_name(self, ledger_id: str, name: str) -> int:
        cursor = self._db.execute(
            "UPDATE LedgerRule SET active=0 WHERE ledgerId=? AND name=? AND active=1",
            (ledger_id, name),
        )
        self._db.commit()
        return cursor.rowcount

    def deactivate_rule(self, ledger_id: str, rule_id: str) -> bool:
        cursor = self._db.execute(
            "UPDATE LedgerRule SET active=0 WHERE ledgerId=? AND id=?", (ledger_id, rule_id)
        )
        self._db.commit()
        return cursor.rowcount > 0

    # ── Import batches ───────────────────────────────────────────────────────
    def insert_import_batch(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = dict(record)
        payload.setdefault("createdAt", now_iso())
        self._db.execute(
            """INSERT INTO LedgerImportBatch
               (id, ledgerId, accountCode, source, format, batchRef, rowCount, postedCount,
                duplicateCount, errorCount, status, detail, createdBy, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payload["id"], payload["ledgerId"], payload["accountCode"],
             payload.get("source") or "import", payload["format"], payload.get("batchRef"),
             int(payload.get("rowCount") or 0), int(payload.get("postedCount") or 0),
             int(payload.get("duplicateCount") or 0), int(payload.get("errorCount") or 0),
             payload.get("status") or "COMPLETE", _dumps(payload.get("detail")),
             payload.get("createdBy"), payload["createdAt"]),
        )
        self._db.commit()
        return payload

    def list_import_batches(self, ledger_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM LedgerImportBatch WHERE ledgerId=? ORDER BY createdAt DESC LIMIT ?",
            (ledger_id, max(1, min(int(limit or 50), 500))),
        ).fetchall()
        return [self._batch_row(row) for row in rows]

    def get_import_batch(self, batch_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM LedgerImportBatch WHERE id=?", (batch_id,)
        ).fetchone()
        return self._batch_row(row) if row else None

    @staticmethod
    def _batch_row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "ledgerId": row["ledgerId"],
            "accountCode": row["accountCode"],
            "source": row["source"],
            "format": row["format"],
            "batchRef": row["batchRef"],
            "rowCount": int(row["rowCount"]),
            "postedCount": int(row["postedCount"]),
            "duplicateCount": int(row["duplicateCount"]),
            "errorCount": int(row["errorCount"]),
            "status": row["status"],
            "detail": _loads(row["detail"], {}),
            "createdBy": row["createdBy"],
            "createdAt": row["createdAt"],
        }

    # ── Reconciliations ──────────────────────────────────────────────────────
    def insert_reconciliation(self, record: dict[str, Any],
                               items: Sequence[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(record)
        payload.setdefault("createdAt", now_iso())
        self._db.execute(
            """INSERT INTO LedgerReconciliation
               (id, ledgerId, accountCode, startDate, endDate, statementBalance,
                openingBalance, closingBalance, difference, tolerance, matchedCount,
                mismatchCount, missingCount, unknownCount, status, detail, createdBy, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payload["id"], payload["ledgerId"], payload["accountCode"],
             payload.get("startDate"), payload.get("endDate"), payload.get("statementBalance"),
             payload.get("openingBalance"), payload.get("closingBalance"),
             payload.get("difference"), payload.get("tolerance") or "0.01000000",
             int(payload.get("matchedCount") or 0), int(payload.get("mismatchCount") or 0),
             int(payload.get("missingCount") or 0), int(payload.get("unknownCount") or 0),
             payload.get("status") or "UNKNOWN", _dumps(payload.get("detail")),
             payload.get("createdBy"), payload["createdAt"]),
        )
        for item in items:
            self._db.execute(
                """INSERT INTO LedgerReconciliationItem
                   (id, reconciliationId, ledgerId, rowNo, entryDate, description, amount,
                    status, method, entryId, detail)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item["id"], payload["id"], payload["ledgerId"], item.get("rowNo"),
                 item.get("entryDate"), item.get("description"), item.get("amount"),
                 item["status"], item.get("method"), item.get("entryId"),
                 _dumps(item.get("detail"))),
            )
        self._db.commit()
        return payload

    def list_reconciliations(self, ledger_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM LedgerReconciliation WHERE ledgerId=? ORDER BY createdAt DESC LIMIT ?",
            (ledger_id, max(1, min(int(limit or 50), 500))),
        ).fetchall()
        return [self._recon_row(row) for row in rows]

    def get_reconciliation(self, reconciliation_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM LedgerReconciliation WHERE id=?", (reconciliation_id,)
        ).fetchone()
        if row is None:
            return None
        payload = self._recon_row(row)
        items = self._db.execute(
            "SELECT * FROM LedgerReconciliationItem WHERE reconciliationId=? ORDER BY rowNo",
            (reconciliation_id,),
        ).fetchall()
        payload["items"] = [
            {
                "rowNo": item["rowNo"],
                "entryDate": item["entryDate"],
                "description": item["description"],
                "amount": item["amount"],
                "status": item["status"],
                "method": item["method"],
                "entryId": item["entryId"],
                "detail": _loads(item["detail"], {}),
            }
            for item in items
        ]
        return payload

    @staticmethod
    def _recon_row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "ledgerId": row["ledgerId"],
            "accountCode": row["accountCode"],
            "startDate": row["startDate"],
            "endDate": row["endDate"],
            "statementBalance": row["statementBalance"],
            "openingBalance": row["openingBalance"],
            "closingBalance": row["closingBalance"],
            "difference": row["difference"],
            "tolerance": row["tolerance"],
            "matchedCount": int(row["matchedCount"]),
            "mismatchCount": int(row["mismatchCount"]),
            "missingCount": int(row["missingCount"]),
            "unknownCount": int(row["unknownCount"]),
            "status": row["status"],
            "detail": _loads(row["detail"], {}),
            "createdBy": row["createdBy"],
            "createdAt": row["createdAt"],
        }

    # ── Schedules ────────────────────────────────────────────────────────────
    def insert_schedule(self, schedule: Any) -> dict[str, Any]:
        from .schedules import Schedule  # noqa: PLC0415

        assert isinstance(schedule, Schedule)
        self._db.execute(
            """INSERT INTO LedgerSchedule
               (id, ledgerId, kind, name, method, startDate, periods, cost, salvage,
                expenseAccount, contraAccount, currency, factor, status, postedThrough,
                createdBy, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (schedule.id, schedule.ledger_id, schedule.kind, schedule.name, schedule.method,
             schedule.start_date, int(schedule.periods), f"{schedule.cost:f}",
             f"{schedule.salvage:f}", schedule.expense_account, schedule.contra_account,
             schedule.currency, f"{schedule.factor:f}", schedule.status,
             int(schedule.posted_through), schedule.created_by,
             schedule.created_at or now_iso()),
        )
        self._db.commit()
        return schedule.to_dict()

    def _schedule_row(self, row: Any) -> Any:
        from .schedules import build_schedule  # noqa: PLC0415

        schedule = build_schedule(
            row["ledgerId"],
            name=row["name"],
            kind=row["kind"],
            cost=row["cost"],
            periods=int(row["periods"]),
            expense_account=row["expenseAccount"],
            contra_account=row["contraAccount"],
            start_date=row["startDate"],
            salvage=row["salvage"],
            method=row["method"],
            factor=row["factor"],
            currency=row["currency"],
            schedule_id=row["id"],
            created_at=row["createdAt"],
        )
        schedule.status = row["status"]
        schedule.posted_through = int(row["postedThrough"])
        schedule.created_by = row["createdBy"]
        return schedule

    def list_schedules(self, ledger_id: str, *, active_only: bool = True) -> list[Any]:
        sql = "SELECT * FROM LedgerSchedule WHERE ledgerId=?"
        if active_only:
            sql += " AND status='ACTIVE'"
        sql += " ORDER BY startDate, name"
        return [self._schedule_row(row)
                for row in self._db.execute(sql, (ledger_id,)).fetchall()]

    def get_schedule(self, schedule_id: str) -> Optional[Any]:
        row = self._db.execute(
            "SELECT * FROM LedgerSchedule WHERE id=?", (schedule_id,)
        ).fetchone()
        return self._schedule_row(row) if row else None

    def set_schedule_progress(self, schedule_id: str, posted_through: int,
                              status: str) -> None:
        self._db.execute(
            "UPDATE LedgerSchedule SET postedThrough=?, status=? WHERE id=?",
            (int(posted_through), status, schedule_id),
        )
        self._db.commit()

    # ── Close runs ───────────────────────────────────────────────────────────
    def insert_close_run(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = dict(record)
        payload.setdefault("createdAt", now_iso())
        self._db.execute(
            """INSERT INTO LedgerCloseRun
               (id, ledgerId, periodId, startDate, endDate, status, blockerCount,
                warningCount, detail, createdBy, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payload["id"], payload["ledgerId"], payload.get("periodId"),
             payload.get("startDate"), payload.get("endDate"), payload["status"],
             int(payload.get("blockerCount") or 0), int(payload.get("warningCount") or 0),
             _dumps(payload.get("detail")), payload.get("createdBy"), payload["createdAt"]),
        )
        self._db.commit()
        return self._close_row(
            self._db.execute("SELECT * FROM LedgerCloseRun WHERE id=?",
                             (payload["id"],)).fetchone()
        )

    @staticmethod
    def _close_row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "ledgerId": row["ledgerId"],
            "periodId": row["periodId"],
            "startDate": row["startDate"],
            "endDate": row["endDate"],
            "status": row["status"],
            "blockerCount": int(row["blockerCount"]),
            "warningCount": int(row["warningCount"]),
            "detail": _loads(row["detail"], {}),
            "createdBy": row["createdBy"],
            "createdAt": row["createdAt"],
        }

    def list_close_runs(self, ledger_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM LedgerCloseRun WHERE ledgerId=? ORDER BY createdAt DESC LIMIT ?",
            (ledger_id, max(1, min(int(limit or 50), 500))),
        ).fetchall()
        return [self._close_row(row) for row in rows]

    def get_close_run(self, run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM LedgerCloseRun WHERE id=?", (run_id,)
        ).fetchone()
        return self._close_row(row) if row else None

    # ── Audit ────────────────────────────────────────────────────────────────
    def audit(self, ledger_id: str, kind: str, *, subject_id: Optional[str] = None,
              actor: Optional[str] = None, detail: Optional[dict[str, Any]] = None,
              event_id: Optional[str] = None) -> str:
        import uuid

        event = event_id or f"lev_{uuid.uuid4().hex[:20]}"
        self._db.execute(
            """INSERT INTO LedgerAuditEvent (id, ledgerId, kind, subjectId, actor, detail, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event, ledger_id, kind, subject_id, actor, _dumps(detail), now_iso()),
        )
        self._db.commit()
        return event

    def list_audit(self, ledger_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM LedgerAuditEvent WHERE ledgerId=? ORDER BY createdAt DESC LIMIT ?",
            (ledger_id, max(1, min(int(limit or 100), 500))),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "subjectId": row["subjectId"],
                "actor": row["actor"],
                "detail": _loads(row["detail"], {}),
                "createdAt": row["createdAt"],
            }
            for row in rows
        ]


__all__ = ["LedgerStore"]
