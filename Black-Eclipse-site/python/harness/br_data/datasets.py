"""One entry point for the Brazilian official datasets beyond COTAHIST.

`DATASETS` is the single list an operator surface (or a tool) reads to know what
exists, where it comes from, and what a parse produces. Keeping it declarative
means adding a dataset is a row here plus a parser module — not edits in a route,
a tool and a doc.

Each entry states its **shape** honestly: `single` (one paper's row per bond per
day), `series` (one code's observations), `funds` (one row per fund per day).
Nothing here downloads; `parse_dataset` is a pure function of bytes.
"""

from __future__ import annotations

from typing import Any, Callable

from . import bcb, cotahist, cvm, tesouro
from .csvtext import DatasetError

DATASETS: dict[str, dict[str, Any]] = {
    "cotahist": {
        "label": "B3 COTAHIST (daily quotes)",
        "shape": "quotes",
        "source": "B3",
        "transport": "zip",
        "url": "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP",
        "module": "harness.br_data.cotahist",
    },
    cvm.DATASET: {
        "label": "CVM daily fund report (quota, net assets, flows)",
        "shape": "funds",
        "source": "CVM",
        "transport": "zip-of-csv",
        "url": cvm.URL_TEMPLATE,
        "module": "harness.br_data.cvm",
    },
    bcb.DATASET: {
        "label": "BCB SGS time series",
        "shape": "series",
        "source": "Banco Central do Brasil",
        "transport": "json",
        "url": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados?formato=json",
        "module": "harness.br_data.bcb",
    },
    tesouro.DATASET: {
        "label": "Tesouro Direto prices and yields",
        "shape": "single",
        "source": "Tesouro Transparente",
        "transport": "csv",
        "url": tesouro.URL,
        "module": "harness.br_data.tesouro",
    },
}


def list_datasets() -> list[dict[str, Any]]:
    """Every dataset, with its declared source and shape (no rows)."""
    return [{"id": key, **value} for key, value in DATASETS.items()]


def _parser(name: str) -> Callable[..., Any]:
    if name == "cotahist":
        return cotahist.parse_records
    if name == cvm.DATASET:
        return cvm.parse
    if name == tesouro.DATASET:
        return tesouro.parse
    if name == bcb.DATASET:
        return bcb.parse
    raise DatasetError("UNKNOWN_DATASET", f"no parser for {name!r}")


def parse_dataset(name: str, payload: bytes | str, **options: Any) -> Any:
    """Parse `payload` with the dataset's own parser.

    `bcb_sgs` requires `code=` (the series); every other dataset ignores options,
    so a caller cannot silently pass an argument that has no effect.
    """
    if name not in DATASETS:
        raise DatasetError("UNKNOWN_DATASET", f"no parser for {name!r}")
    if name == bcb.DATASET:
        code = options.get("code")
        if not isinstance(code, int):
            raise DatasetError("SERIES_CODE_REQUIRED", "bcb_sgs needs an integer series `code`")
        return bcb.parse(payload, code)
    return _parser(name)(payload)


__all__ = ["DATASETS", "list_datasets", "parse_dataset"]
