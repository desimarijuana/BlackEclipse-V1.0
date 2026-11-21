"""BCB SGS — Banco Central time series, parsed from the JSON the API returns.

`api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados?formato=json` answers with an
array of one point per observation::

    [{"data": "01/11/2026", "valor": "5,4321"}, ...]

Two things the payload does *not* tell you, and this module refuses to invent:

  * **the series name.** It is not in the response. `SERIES` maps only the codes
    whose meaning is stable and documented; an unmapped code returns
    `label=None` rather than a plausible-sounding guess.
  * **a missing value.** A blank or non-numeric `valor` is **skipped and
    counted**, never coerced to 0: a zero Selic rate is a very different claim
    from an unreported one.

Dates arrive `dd/mm/yyyy`; the output is ISO so it sorts and joins.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .csvtext import DatasetError, iso_date, number

DATASET = "bcb_sgs"

#: Only codes whose meaning is documented and stable. An unknown code is honest
#: about being unknown.
SERIES: dict[int, dict[str, str]] = {
    1: {"name": "USD/BRL PTAX (sell)", "unit": "BRL", "frequency": "daily"},
    11: {"name": "Selic effective daily rate", "unit": "% per day", "frequency": "daily"},
    12: {"name": "CDI daily rate", "unit": "% per day", "frequency": "daily"},
    432: {"name": "Selic target rate", "unit": "% per year", "frequency": "daily"},
    433: {"name": "IPCA (monthly inflation)", "unit": "% per month", "frequency": "monthly"},
    4389: {"name": "Broad money M2", "unit": "BRL million", "frequency": "monthly"},
}


def url_for(code: int, *, start: str = "", end: str = "") -> str:
    """The SGS URL, with the optional `dd/mm/yyyy` window BCB expects."""
    base = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{int(code)}/dados?formato=json"
    params = []
    if start:
        params.append(f"dataInicial={start}")
    if end:
        params.append(f"dataFinal={end}")
    return base + ("&" + "&".join(params) if params else "")


def describe(code: int) -> dict[str, Any]:
    """Series metadata, with `label: None` for a code this module does not know."""
    known = SERIES.get(int(code))
    return {
        "dataset": DATASET,
        "code": int(code),
        "label": known["name"] if known else None,
        "unit": known["unit"] if known else None,
        "frequency": known["frequency"] if known else None,
        "known": known is not None,
    }


def parse(payload: bytes | str, code: int) -> dict[str, Any]:
    """Parse an SGS response into `{points, skipped, meta}`.

    `skipped` is a count of observations the publisher left blank — reported so a
    consumer can see a gap instead of reading a shorter series as a complete one.
    """
    if isinstance(payload, (bytes, bytearray)):
        payload = bytes(payload).decode("utf-8-sig", errors="replace")
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise DatasetError("BAD_JSON", "the SGS response is not JSON") from exc
    if isinstance(data, dict):  # BCB answers errors as an object
        raise DatasetError(
            "BCB_ERROR",
            str(data.get("error") or data.get("message") or "SGS returned an object")[:300],
        )
    if not isinstance(data, list):
        raise DatasetError("BAD_SHAPE", "the SGS response is not an array of points")
    points: list[dict[str, Any]] = []
    skipped = 0
    for index, point in enumerate(data, start=1):
        if not isinstance(point, dict):
            skipped += 1
            continue
        value = number(point.get("valor"))
        observed = iso_date(point.get("data"))
        if value is None or not observed:
            skipped += 1
            continue
        points.append({"date": observed, "value": value, "series": int(code)})
    if not points and not skipped:
        raise DatasetError("NO_ROWS", "the SGS response carries no observations")
    return {"points": points, "skipped": skipped, "meta": describe(code)}


__all__ = ["DATASET", "SERIES", "describe", "parse", "url_for"]
