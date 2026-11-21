"""Storage for the CVM / BCB / Tesouro rows, keyed so a re-sync is a no-op.

Each dataset keeps its own table because their natural keys differ — a fund is
`(cnpj, date)`, a series is `(series, date)`, a bond is `(bond, date)` — and
squashing them into one table would lose exactly the key that makes re-syncing
idempotent.

The rules are the store's existing rules, applied here:

  * a row missing part of its key is **skipped and counted**, never written under
    an empty key;
  * a **derived** value (`cvm netFlow`) is not stored: it is arithmetic over
    stored columns and would go stale if the derivation changed. Readers derive
    it from `contributions - redemptions`;
  * a blank price stays `NULL`, so "not reported" is distinguishable from `0.0`.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS cvm_funds (
    cnpj           TEXT NOT NULL,
    trade_date     TEXT NOT NULL,
    fund_type      TEXT,
    total_value    REAL,
    quota_value    REAL,
    net_assets     REAL,
    contributions  REAL,
    redemptions    REAL,
    holders        REAL,
    PRIMARY KEY (cnpj, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_cvm_funds_date ON cvm_funds(trade_date);

CREATE TABLE IF NOT EXISTS bcb_series (
    series     INTEGER NOT NULL,
    trade_date TEXT NOT NULL,
    value      REAL NOT NULL,
    PRIMARY KEY (series, trade_date)
);

CREATE TABLE IF NOT EXISTS tesouro_bonds (
    bond        TEXT NOT NULL,
    trade_date  TEXT NOT NULL,
    family      TEXT,
    maturity    TEXT,
    buy_yield   REAL,
    sell_yield  REAL,
    buy_price   REAL,
    sell_price  REAL,
    base_price  REAL,
    PRIMARY KEY (bond, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_tesouro_date ON tesouro_bonds(trade_date);
"""

#: dataset id -> (table, key columns, [(column, row key)])
SPEC: dict[str, dict[str, Any]] = {
    "cvm_inf_diario": {
        "table": "cvm_funds",
        "key": ("cnpj", "trade_date"),
        "columns": [
            ("cnpj", "cnpj"),
            ("trade_date", "date"),
            ("fund_type", "fundType"),
            ("total_value", "totalValue"),
            ("quota_value", "quotaValue"),
            ("net_assets", "netAssets"),
            ("contributions", "contributions"),
            ("redemptions", "redemptions"),
            ("holders", "holders"),
        ],
    },
    "bcb_sgs": {
        "table": "bcb_series",
        "key": ("series", "trade_date"),
        "columns": [
            ("series", "series"),
            ("trade_date", "date"),
            ("value", "value"),
        ],
    },
    "tesouro_direto_preco_taxa": {
        "table": "tesouro_bonds",
        "key": ("bond", "trade_date"),
        "columns": [
            ("bond", "bond"),
            ("trade_date", "date"),
            ("family", "family"),
            ("maturity", "maturity"),
            ("buy_yield", "buyYield"),
            ("sell_yield", "sellYield"),
            ("buy_price", "buyPrice"),
            ("sell_price", "sellPrice"),
            ("base_price", "basePrice"),
        ],
    },
}


def upsert(conn: Any, name: str, rows: Iterable[dict[str, Any]]) -> tuple[int, int, int]:
    """Insert/update `rows` for dataset `name`. Returns (inserted, updated, skipped).

    An unknown dataset raises `KeyError`: silently accepting rows nothing can
    read back would be data loss disguised as success.
    """
    spec = SPEC[name]
    columns = [column for column, _row_key in spec["columns"]]
    row_keys = [row_key for _column, row_key in spec["columns"]]
    placeholders = ", ".join("?" for _ in columns)
    update_clause = ", ".join(
        f"{column}=excluded.{column}" for column in columns if column not in spec["key"])
    key_columns = ", ".join(spec["key"])
    sql = (
        f"INSERT INTO {spec['table']} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT({key_columns}) DO UPDATE SET {update_clause}"
    )
    key_indexes = [columns.index(column) for column in spec["key"]]
    inserted = updated = skipped = 0
    for row in rows:
        values = [row.get(row_key) for row_key in row_keys]
        if any(values[index] in (None, "") for index in key_indexes):
            skipped += 1
            continue
        exists = conn.execute(
            f"SELECT 1 FROM {spec['table']} WHERE " + " AND ".join(f"{c}=?" for c in spec["key"]),
            tuple(values[index] for index in key_indexes),
        ).fetchone()
        conn.execute(sql, values)
        if exists:
            updated += 1
        else:
            inserted += 1
    return inserted, updated, skipped


def counts(conn: Any) -> dict[str, int]:
    """Row count per dataset table (a table never written counts 0)."""
    out: dict[str, int] = {}
    for name, spec in SPEC.items():
        out[name] = int(conn.execute(f"SELECT COUNT(*) FROM {spec['table']}").fetchone()[0])
    return out


def read(
    conn: Any,
    name: str,
    *,
    key: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Rows of one dataset, newest first; `key` filters on the first key column.

    `key` is the fund CNPJ, the BCB series code (as a string) or the bond name —
    always the first half of that dataset's natural key.
    """
    spec = SPEC[name]
    first_key = spec["key"][0]
    sql = f"SELECT * FROM {spec['table']} ORDER BY trade_date DESC LIMIT ?"
    params: list[Any] = [int(limit)]
    if key not in (None, ""):
        sql = (
            f"SELECT * FROM {spec['table']} WHERE {first_key}=? "
            "ORDER BY trade_date DESC LIMIT ?"
        )
        params = [key, int(limit)]
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


__all__ = ["SCHEMA", "SPEC", "counts", "read", "upsert"]
