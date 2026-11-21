"""Tesouro Direto — the published government-bond price and yield file.

Tesouro Transparente publishes `PrecoTaxaTesouroDireto.csv`: one row per bond per
business day, with the morning buy/sell yields and the corresponding unit prices.

Published header (`,`-or-`;`-delimited, decimal comma, `dd/mm/yyyy` dates)::

    Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;
    PU Compra Mania;PU Venda Mania;PU Base Mania

`PU … Mania` is the publisher's own typo for *Manhã* (morning) and appears in the
real file, so it is accepted alongside the corrected spelling. Yields are **% per
year** exactly as published (not decimals), and this module does not annualize,
compound or "fix" them — converting 12.5% to 0.125 would silently change what the
number means.

A price of `0,00` is real (the bond was not offered for that side); it is kept as
`0.0`. A **blank** cell is `None`, because that means the publisher said nothing.
"""

from __future__ import annotations

from typing import Any, Optional

from .csvtext import DatasetError, decode, iso_date, number, pick, rows

DATASET = "tesouro_direto_preco_taxa"
URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv"
)

#: The bond families in the file, verbatim. Naming them here means a typo in a
#: fixture fails a test instead of becoming a new "family".
FAMILIES = ("Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+", "Tesouro IGPM+")


def family(bond: str) -> str:
    """The family a bond belongs to, or `""` when it matches none of them."""
    text = str(bond or "").strip()
    for name in FAMILIES:
        if text.startswith(name):
            return name
    return ""


def parse_row(row: dict[str, str]) -> Optional[dict[str, Any]]:
    """Normalize one published row. `None` when it names no bond."""
    bond = pick(row, "Tipo Titulo", "Tipo Título").strip()
    if not bond:
        return None
    return {
        "dataset": DATASET,
        "bond": bond,
        "family": family(bond),
        "maturity": iso_date(pick(row, "Data Vencimento")),
        "date": iso_date(pick(row, "Data Base")),
        "buyYield": number(pick(row, "Taxa Compra Manha", "Taxa Compra Manhã")),
        "sellYield": number(pick(row, "Taxa Venda Manha", "Taxa Venda Manhã")),
        "buyPrice": number(pick(row, "PU Compra Mania", "PU Compra Manhã")),
        "sellPrice": number(pick(row, "PU Venda Mania", "PU Venda Manhã")),
        "basePrice": number(pick(row, "PU Base Mania", "PU Base Manhã")),
        "yieldUnit": "% per year",
    }


def parse(raw: bytes | str) -> list[dict[str, Any]]:
    """Parse the whole file (bytes or text) into normalized rows."""
    text = decode(raw)
    if not text.strip():
        raise DatasetError("EMPTY", "the Tesouro file is empty")
    delimiter = ";" if text.splitlines()[0].count(";") >= 4 else ","
    parsed: list[dict[str, Any]] = []
    for index, row in enumerate(rows(text, delimiter=delimiter), start=2):
        try:
            normalized = parse_row(row)
        except DatasetError as exc:
            raise DatasetError(exc.code, f"line {index}: {exc.message}") from exc
        if normalized is not None:
            parsed.append(normalized)
    if not parsed:
        raise DatasetError("NO_ROWS", "the file has a header but no bond rows")
    return parsed


__all__ = ["DATASET", "FAMILIES", "URL", "family", "parse", "parse_row"]
