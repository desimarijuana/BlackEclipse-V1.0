"""AR/AP subledger persistence on the ONE `agent-memory.db` connection.

Separate from `LedgerStore` only to keep both files readable — it is the SAME
database, the SAME `AgentMemoryStore` connection, and no second source of truth.
Documents are immutable once posted: a void reverses the journal entry and flips
the status; it never edits the amounts.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional, Sequence

from ..persistence import now_iso
from .errors import DOCUMENT_NOT_FOUND, LedgerError
from .money import D, ZERO

_SCHEMA = """
CREATE TABLE IF NOT EXISTS LedgerParty (
  id                 TEXT PRIMARY KEY,
  ledgerId           TEXT NOT NULL,
  name               TEXT NOT NULL,
  kind               TEXT NOT NULL,
  email              TEXT,
  taxId              TEXT,
  currency           TEXT NOT NULL DEFAULT '',
  paymentTermsDays   INTEGER NOT NULL DEFAULT 30,
  active             INTEGER NOT NULL DEFAULT 1,
  createdAt          TEXT NOT NULL,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ledger_party ON LedgerParty(ledgerId, kind);

CREATE TABLE IF NOT EXISTS LedgerTaxCode (
  id                TEXT PRIMARY KEY,
  ledgerId          TEXT NOT NULL,
  code              TEXT NOT NULL,
  name              TEXT NOT NULL,
  jurisdiction      TEXT NOT NULL,
  rate              TEXT NOT NULL,
  kind              TEXT NOT NULL DEFAULT 'VAT',
  accountCode       TEXT NOT NULL,
  priceIncludesTax  INTEGER NOT NULL DEFAULT 0,
  active            INTEGER NOT NULL DEFAULT 1,
  createdAt         TEXT NOT NULL,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_tax_code ON LedgerTaxCode(ledgerId, code);

CREATE TABLE IF NOT EXISTS LedgerDocument (
  id             TEXT PRIMARY KEY,
  ledgerId       TEXT NOT NULL,
  kind           TEXT NOT NULL,
  number         TEXT NOT NULL,
  partyId        TEXT NOT NULL,
  partyName      TEXT NOT NULL,
  issueDate      TEXT NOT NULL,
  dueDate        TEXT NOT NULL,
  currency       TEXT NOT NULL,
  fxRate         TEXT,
  linesJson      TEXT NOT NULL DEFAULT '[]',
  subtotal       TEXT NOT NULL DEFAULT '0',
  taxTotal       TEXT NOT NULL DEFAULT '0',
  total          TEXT NOT NULL DEFAULT '0',
  controlAccount TEXT NOT NULL DEFAULT '',
  status         TEXT NOT NULL DEFAULT 'POSTED',
  journalEntryId TEXT,
  memo           TEXT,
  reference      TEXT,
  createdBy      TEXT,
  createdAt      TEXT NOT NULL,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_document_number
  ON LedgerDocument(ledgerId, kind, number);
CREATE INDEX IF NOT EXISTS idx_ledger_document ON LedgerDocument(ledgerId, kind, status);

CREATE TABLE IF NOT EXISTS LedgerAllocation (
  id          TEXT PRIMARY KEY,
  ledgerId    TEXT NOT NULL,
  documentId  TEXT NOT NULL,
  entryId     TEXT,
  date        TEXT NOT NULL,
  amount      TEXT NOT NULL,
  createdAt   TEXT NOT NULL,
  FOREIGN KEY (ledgerId) REFERENCES Ledger(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ledger_allocation ON LedgerAllocation(documentId);
"""


def _loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value or [], ensure_ascii=False, default=str)


def _dec(value: Any) -> Any:
    return D(value) if value not in (None, "") else ZERO


class SubledgerStore:
    """Parties, tax codes, AR/AP documents and their payment allocations."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self) -> sqlite3.Connection:
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # ── Parties ──────────────────────────────────────────────────────────────
    def insert_party(self, party: Any) -> dict[str, Any]:
        self._db.execute(
            """INSERT INTO LedgerParty
               (id, ledgerId, name, kind, email, taxId, currency, paymentTermsDays,
                active, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (party.id, party.ledger_id, party.name, party.kind, party.email,
             party.tax_id, party.currency, int(party.payment_terms_days),
             int(party.active), party.created_at or now_iso()),
        )
        self._db.commit()
        return party.to_dict()

    def list_parties(self, ledger_id: str, *, kind: Optional[str] = None,
                     active_only: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM LedgerParty WHERE ledgerId=?"
        args: list[Any] = [ledger_id]
        if kind:
            sql += " AND kind=?"
            args.append(str(kind).upper())
        if active_only:
            sql += " AND active=1"
        sql += " ORDER BY name"
        return [self._party_row(row) for row in self._db.execute(sql, tuple(args)).fetchall()]

    def get_party(self, party_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM LedgerParty WHERE id=?", (party_id,)).fetchone()
        return self._party_row(row) if row else None

    @staticmethod
    def _party_row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "ledgerId": row["ledgerId"],
            "name": row["name"],
            "kind": row["kind"],
            "email": row["email"],
            "taxId": row["taxId"],
            "currency": row["currency"],
            "paymentTermsDays": int(row["paymentTermsDays"]),
            "active": bool(row["active"]),
            "createdAt": row["createdAt"],
        }

    # ── Tax codes ─────────────────────────────────────────────────────────────
    def insert_tax_code(self, code: Any) -> dict[str, Any]:
        self._db.execute(
            """INSERT INTO LedgerTaxCode
               (id, ledgerId, code, name, jurisdiction, rate, kind, accountCode,
                priceIncludesTax, active, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code.id, code.ledger_id, code.code, code.name, code.jurisdiction,
             f"{code.rate:f}", code.kind, code.account_code,
             int(code.price_includes_tax), int(code.active), code.created_at or now_iso()),
        )
        self._db.commit()
        return code.to_dict()

    def list_tax_codes(self, ledger_id: str, *, active_only: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM LedgerTaxCode WHERE ledgerId=?"
        if active_only:
            sql += " AND active=1"
        sql += " ORDER BY jurisdiction, code"
        return [self._tax_row(row) for row in self._db.execute(sql, (ledger_id,)).fetchall()]

    def get_tax_code(self, ledger_id: str, code: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM LedgerTaxCode WHERE ledgerId=? AND code=?",
            (ledger_id, str(code).strip().upper()),
        ).fetchone()
        return self._tax_row(row) if row else None

    @staticmethod
    def _tax_row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "ledgerId": row["ledgerId"],
            "code": row["code"],
            "name": row["name"],
            "jurisdiction": row["jurisdiction"],
            "rate": row["rate"],
            "kind": row["kind"],
            "accountCode": row["accountCode"],
            "priceIncludesTax": bool(row["priceIncludesTax"]),
            "active": bool(row["active"]),
            "createdAt": row["createdAt"],
        }

    def deactivate_tax_code(self, ledger_id: str, code: str) -> bool:
        cursor = self._db.execute(
            "UPDATE LedgerTaxCode SET active=0 WHERE ledgerId=? AND code=?",
            (ledger_id, str(code).strip().upper()),
        )
        self._db.commit()
        return cursor.rowcount > 0

    # ── Documents ─────────────────────────────────────────────────────────────
    def next_document_number(self, ledger_id: str, kind: str) -> str:
        prefix = {"INVOICE": "INV", "BILL": "BILL"}.get(str(kind).upper(), "DOC")
        rows = self._db.execute(
            "SELECT number FROM LedgerDocument WHERE ledgerId=? AND kind=?",
            (ledger_id, str(kind).upper()),
        ).fetchall()
        highest = 0
        for row in rows:
            text = str(row["number"] or "")
            if not text.startswith(f"{prefix}-"):
                continue
            try:
                highest = max(highest, int(text[len(prefix) + 1:]))
            except ValueError:
                continue
        return f"{prefix}-{highest + 1:04d}"

    def document_number_exists(self, ledger_id: str, kind: str, number: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM LedgerDocument WHERE ledgerId=? AND kind=? AND number=?",
            (ledger_id, str(kind).upper(), str(number)),
        ).fetchone()
        return row is not None

    def insert_document(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = dict(record)
        payload.setdefault("createdAt", now_iso())
        self._db.execute(
            """INSERT INTO LedgerDocument
               (id, ledgerId, kind, number, partyId, partyName, issueDate, dueDate,
                currency, fxRate, linesJson, subtotal, taxTotal, total, controlAccount,
                status, journalEntryId, memo, reference, createdBy, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payload["id"], payload["ledgerId"], payload["kind"], payload["number"],
             payload["partyId"], payload["partyName"], payload["issueDate"],
             payload["dueDate"], payload["currency"], payload.get("fxRate"),
             _dumps(payload.get("lines")), payload.get("subtotal") or "0",
             payload.get("taxTotal") or "0", payload.get("total") or "0",
             payload.get("controlAccount") or "",
             payload.get("status") or "POSTED", payload.get("journalEntryId"),
             payload.get("memo"), payload.get("reference"), payload.get("createdBy"),
             payload["createdAt"]),
        )
        self._db.commit()
        return payload

    def get_document(self, document_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM LedgerDocument WHERE id=?", (document_id,)
        ).fetchone()
        return self._document_row(row) if row else None

    def require_document(self, document_id: str) -> dict[str, Any]:
        document = self.get_document(document_id)
        if document is None:
            raise LedgerError(DOCUMENT_NOT_FOUND, f"document {document_id} not found",
                              {"documentId": document_id})
        return document

    def list_documents(
        self,
        ledger_id: str,
        *,
        kind: Optional[str] = None,
        party_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM LedgerDocument WHERE ledgerId=?"
        args: list[Any] = [ledger_id]
        if kind:
            sql += " AND kind=?"
            args.append(str(kind).upper())
        if party_id:
            sql += " AND partyId=?"
            args.append(party_id)
        if status:
            sql += " AND status=?"
            args.append(str(status).upper())
        sql += " ORDER BY issueDate DESC, number DESC LIMIT ?"
        args.append(max(1, min(int(limit or 100), 1000)))
        return [self._document_row(row) for row in self._db.execute(sql, tuple(args)).fetchall()]

    def set_document_status(self, document_id: str, status: str) -> None:
        self._db.execute(
            "UPDATE LedgerDocument SET status=? WHERE id=?", (status, document_id)
        )
        self._db.commit()

    def _document_row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "ledgerId": row["ledgerId"],
            "kind": row["kind"],
            "number": row["number"],
            "partyId": row["partyId"],
            "partyName": row["partyName"],
            "issueDate": row["issueDate"],
            "dueDate": row["dueDate"],
            "currency": row["currency"],
            "fxRate": row["fxRate"],
            "lines": _loads(row["linesJson"], []),
            "subtotal": row["subtotal"],
            "taxTotal": row["taxTotal"],
            "total": row["total"],
            "controlAccount": row["controlAccount"] if "controlAccount" in row.keys() else "",
            "status": row["status"],
            "journalEntryId": row["journalEntryId"],
            "memo": row["memo"],
            "reference": row["reference"],
            "createdBy": row["createdBy"],
            "createdAt": row["createdAt"],
        }

    # ── Allocations ──────────────────────────────────────────────────────────
    def insert_allocation(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = dict(record)
        payload.setdefault("createdAt", now_iso())
        self._db.execute(
            """INSERT INTO LedgerAllocation
               (id, ledgerId, documentId, entryId, date, amount, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (payload["id"], payload["ledgerId"], payload["documentId"],
             payload.get("entryId"), payload["date"], payload["amount"],
             payload["createdAt"]),
        )
        self._db.commit()
        return payload

    def allocations(self, document_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM LedgerAllocation WHERE documentId=? ORDER BY date, createdAt",
            (document_id,),
        ).fetchall()
        return [
            {"id": row["id"], "entryId": row["entryId"], "date": row["date"],
             "amount": row["amount"], "createdAt": row["createdAt"]}
            for row in rows
        ]

    def allocated_total(self, document_id: str, *, as_of: Optional[str] = None) -> Any:
        if as_of:
            rows = self._db.execute(
                "SELECT amount FROM LedgerAllocation WHERE documentId=? AND date<=?",
                (document_id, as_of),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT amount FROM LedgerAllocation WHERE documentId=?",
                (document_id,),
            ).fetchall()
        total = ZERO
        for row in rows:
            total += _dec(row["amount"])
        return total

    # ── Purge ────────────────────────────────────────────────────────────────
    def purge(self, ledger_id: str) -> None:
        for table in ("LedgerAllocation", "LedgerDocument", "LedgerTaxCode", "LedgerParty"):
            self._db.execute(f"DELETE FROM {table} WHERE ledgerId=?", (ledger_id,))
        self._db.commit()


__all__ = ["SubledgerStore"]
