"""CVM open data — the daily fund report (`inf_diario_fi_YYYYMM.csv`).

CVM publishes one file per month at `dados.cvm.gov.br`: every investment fund's
closing quota, net asset value and that day's subscriptions and redemptions.

Published columns (in this order, `;`-delimited, decimal comma)::

    TP_FUNDO;CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST

Semantics worth stating, because they are the ones people get wrong:

  * `VL_QUOTA` is the **quota value**, not the fund's total.
  * `VL_PATRIM_LIQ` is **net assets** (patrimônio líquido), the closest thing to
    AUM in this file.
  * `CAPTC_DIA` / `RESG_DIA` are **that day's** subscriptions and redemptions.
    `netFlow` is their arithmetic difference and is labelled as derived.

A blank cell stays `None`. CVM blanks a field when the fund did not report it
(and a fund with no movement on a day may leave the flow cells empty), so filling
`0.0` would invent trading that did not happen.
"""

from __future__ import annotations

from typing import Any, Optional

from .csvtext import DatasetError, decode, iso_date, number, pick, rows

DATASET = "cvm_inf_diario"
URL_TEMPLATE = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{yyyymm}.zip"
ENCODING = "utf-8-or-latin-1"


def parse_row(row: dict[str, str]) -> Optional[dict[str, Any]]:
    """Normalize one published row. `None` when it carries no fund identity."""
    cnpj = pick(row, "CNPJ_FUNDO", "CNPJ_FUNDO_CLASSE").strip()
    if not cnpj:
        return None
    contributions = number(pick(row, "CAPTC_DIA"))
    redemptions = number(pick(row, "RESG_DIA"))
    net_flow: Optional[float] = None
    if contributions is not None or redemptions is not None:
        net_flow = (contributions or 0.0) - (redemptions or 0.0)
    return {
        "dataset": DATASET,
        "fundType": pick(row, "TP_FUNDO").strip(),
        "cnpj": cnpj,
        "date": iso_date(pick(row, "DT_COMPTC")),
        "totalValue": number(pick(row, "VL_TOTAL")),
        "quotaValue": number(pick(row, "VL_QUOTA")),
        "netAssets": number(pick(row, "VL_PATRIM_LIQ")),
        "contributions": contributions,
        "redemptions": redemptions,
        # Derived, and named so: not a published column.
        "netFlow": net_flow,
        "holders": number(pick(row, "NR_COTST")),
        "derived": ["netFlow"],
    }


def parse(raw: bytes | str) -> list[dict[str, Any]]:
    """Parse a whole monthly file (bytes or text) into normalized rows."""
    text = decode(raw)
    if not text.strip():
        raise DatasetError("EMPTY", "the CVM file is empty")
    parsed: list[dict[str, Any]] = []
    for number_, row in enumerate(rows(text), start=2):
        try:
            normalized = parse_row(row)
        except DatasetError as exc:
            raise DatasetError(exc.code, f"line {number_}: {exc.message}") from exc
        if normalized is not None:
            parsed.append(normalized)
    if not parsed:
        raise DatasetError("NO_ROWS", "the file has a header but no fund rows")
    return parsed


__all__ = ["DATASET", "ENCODING", "URL_TEMPLATE", "parse", "parse_row"]
