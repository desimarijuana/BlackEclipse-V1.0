"""Comparable-company analysis with explicit peer provenance.

Peers are never invented. A peer with a missing or non-positive denominator is
excluded with a recorded reason; the summary states the valid peer count.
"""

from __future__ import annotations

import datetime as _dt
import math
import re
from statistics import mean
from typing import Any, Optional

from .contracts import Check, ModelError, ModelResult, number

METRICS = ("ev_revenue", "ev_ebitda", "ev_ebit", "pe")


def _percentile(values: list[float], fraction: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _month_of(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    match = re.search(r"(?:^|\D)(\d{1,2})[-/](\d{1,2})(?:\D|$)", text)
    if match:
        month = int(match.group(1))
        return month if 1 <= month <= 12 else None
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        month = int(match.group(2))
        return month if 1 <= month <= 12 else None
    return None


def _date_of(value: Any) -> Optional[_dt.date]:
    text = str(value or "").strip()
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return None
    try:
        return _dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _quarterly_ttm(peer: dict[str, Any], *, target_fye: Any) -> Optional[dict[str, Optional[float]]]:
    quarters = peer.get("quarterly")
    if not isinstance(quarters, list) or len(quarters) < 4:
        return None
    parsed: list[tuple[_dt.date, dict[str, Any]]] = []
    for entry in quarters:
        if not isinstance(entry, dict):
            continue
        end = _date_of(entry.get("endDate") or entry.get("period") or entry.get("date"))
        if end is not None:
            parsed.append((end, entry))
    if len(parsed) < 4:
        return None
    parsed.sort(key=lambda item: item[0])
    target_month_day = str(target_fye or "").strip()
    match = re.search(r"(\d{1,2})[-/](\d{1,2})", target_month_day)
    if not match:
        return None
    month, day = int(match.group(1)), int(match.group(2))
    target = _dt.date(parsed[-1][0].year, month, day)
    eligible = [item for item in parsed if item[0] <= target]
    if len(eligible) < 4:
        return None
    window = eligible[-4:]
    if (window[-1][0] - window[0][0]).days > 460:
        return None
    result: dict[str, Optional[float]] = {}
    aliases = {
        "revenue": ("revenue",),
        "ebitda": ("ebitda",),
        "ebit": ("ebit", "operatingIncome", "operating_income"),
        "net_income": ("net_income", "netIncome"),
        "eps": ("eps",),
    }
    for field, names in aliases.items():
        values = []
        for _date, entry in window:
            value = next((entry.get(name) for name in names if entry.get(name) is not None), None)
            if value is None:
                values = []
                break
            values.append(number(value, f"peer.quarterly.{field}"))
        result[field] = sum(values) if values else None
    if result.get("revenue") is None and result.get("ebitda") is None:
        return None
    return result


def _peer_pick(peer: dict[str, Any], *names: str) -> Any:
    for name in names:
        if peer.get(name) is not None:
            return peer[name]
    return None


def _peer_rows(
    peers: list[dict[str, Any]],
    *,
    target_currency: str,
    target_fye: Any,
    fx: dict[str, Any],
    calendarize: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    warnings: list[str] = []
    for index, peer in enumerate(peers):
        if not isinstance(peer, dict):
            excluded.append({"peer": f"peer {index}", "reason": "not an object"})
            continue
        name = str(peer.get("name") or f"Peer {index + 1}")
        if not peer.get("period") or not peer.get("source"):
            warnings.append(f"{name}: period/source not stated; the multiple is shown without provenance")
        currency = str(peer.get("currency") or target_currency or "").upper()
        target = str(target_currency or currency).upper()
        rate = 1.0
        if currency and target and currency != target:
            raw_rate = peer.get("fxRate", peer.get("fx_rate", fx.get(currency)))
            if raw_rate is None:
                excluded.append({
                    "peer": name,
                    "reason": f"currency {currency} differs from target {target} and no fxRate was supplied",
                })
                continue
            rate = number(raw_rate, f"comps.peers[{index}].fxRate")
            if rate <= 0:
                excluded.append({"peer": name, "reason": "fxRate must be positive"})
                continue
        quarterly = _quarterly_ttm(peer, target_fye=target_fye) if calendarize else None
        if quarterly is not None:
            factor = 1.0
            method = "quarterly_ttm"
        else:
            explicit = peer.get("calendarizationFactor", peer.get("calendarization_factor"))
            if explicit is not None:
                factor = number(explicit, f"comps.peers[{index}].calendarizationFactor")
                method = "explicit_factor"
            else:
                peer_month = _month_of(peer.get("fiscalYearEnd") or peer.get("period"))
                target_month = _month_of(target_fye)
                if calendarize and peer_month is not None and target_month is not None and peer_month != target_month:
                    excluded.append({
                        "peer": name,
                        "reason": (
                            "fiscal year end differs from the target and no complete quarterly data or "
                            "explicit calendarizationFactor was supplied"
                        ),
                    })
                    continue
                factor = 1.0
                method = "none"

        price = number(_peer_pick(peer, "price", "sharePrice", "share_price"), f"comps.peers[{index}].price") * rate
        shares = number(_peer_pick(peer, "shares", "sharesOutstanding", "shares_outstanding"), f"comps.peers[{index}].shares")
        debt = number(_peer_pick(peer, "debt", "totalDebt", "total_debt") or 0.0, f"comps.peers[{index}].debt") * rate
        cash = number(_peer_pick(peer, "cash", "cashAndCashEquivalents", "cash_and_cash_equivalents") or 0.0, f"comps.peers[{index}].cash") * rate
        minority = number(peer.get("minority", 0.0), f"comps.peers[{index}].minority") * rate
        preferred = number(peer.get("preferred", 0.0), f"comps.peers[{index}].preferred") * rate
        market_cap = price * shares
        enterprise_value = market_cap + debt - cash + minority + preferred
        row: dict[str, Any] = {
            "name": name,
            "marketCap": market_cap,
            "enterpriseValue": enterprise_value,
            "period": str(_peer_pick(peer, "period", "endDate", "end_date") or ""),
            "source": str(_peer_pick(peer, "source", "statementSource", "statement_source") or ""),
            "currency": target,
            "sourceCurrency": currency,
            "fxRate": rate,
            "calendarizationFactor": factor,
            "calendarizationMethod": method,
            "multiples": {},
        }
        aliases = {
            "revenue": ("revenue", "totalRevenue", "total_revenue"),
            "ebitda": ("ebitda",),
            "ebit": ("ebit", "operatingIncome", "operating_income"),
            "net_income": ("net_income", "netIncome"),
        }
        for metric, names in aliases.items():
            value = quarterly.get(metric) if quarterly else None
            if value is None:
                value = _peer_pick(peer, *names)
            if value is not None:
                row[metric] = number(value, f"comps.peers[{index}].{metric}") * rate * (1.0 if quarterly else factor)
        eps = quarterly.get("eps") if quarterly else None
        if eps is None:
            eps = _peer_pick(peer, "eps", "epsDiluted", "eps_diluted")
        if eps is not None:
            row["eps"] = number(eps, f"comps.peers[{index}].eps") * rate * (1.0 if quarterly else factor)

        if row.get("revenue", 0) > 0:
            row["multiples"]["ev_revenue"] = enterprise_value / row["revenue"]
        else:
            excluded.append({"peer": name, "metric": "ev_revenue", "reason": "revenue is missing or non-positive"})
        if row.get("ebitda", 0) > 0:
            row["multiples"]["ev_ebitda"] = enterprise_value / row["ebitda"]
        else:
            excluded.append({"peer": name, "metric": "ev_ebitda", "reason": "EBITDA is missing or non-positive"})
        if row.get("ebit", 0) > 0:
            row["multiples"]["ev_ebit"] = enterprise_value / row["ebit"]
        else:
            excluded.append({"peer": name, "metric": "ev_ebit", "reason": "EBIT is missing or non-positive"})
        if row.get("eps", 0) > 0:
            row["multiples"]["pe"] = price / row["eps"]
        else:
            excluded.append({"peer": name, "metric": "pe", "reason": "EPS is missing or non-positive"})
        rows.append(row)
    return rows, excluded, warnings


def build_comps(spec: dict[str, Any]) -> ModelResult:
    comps = spec.get("comps")
    if not isinstance(comps, dict):
        raise ModelError("INPUT_UNAVAILABLE", "comps is required for a comparable-company model")
    peers = comps.get("peers")
    if not isinstance(peers, list) or not peers:
        raise ModelError("INPUT_UNAVAILABLE", "comps.peers must be a non-empty array")
    if len(peers) > 100:
        raise ModelError("INPUT_LIMIT", "comps.peers is limited to 100 companies")
    target = comps.get("target")
    if not isinstance(target, dict):
        raise ModelError("INPUT_UNAVAILABLE", "comps.target is required")
    target_metric = str(target.get("metric") or "").strip().lower()
    if target_metric not in ("revenue", "ebitda", "ebit", "net_income"):
        raise ModelError("INPUT_INVALID", "comps.target.metric must be revenue, ebitda, ebit or net_income")
    target_value = number(
        target.get("value", target.get("metricValue", target.get("metric_value"))),
        "comps.target.value",
    )
    net_debt = number(
        target.get("net_debt", target.get("netDebt", 0.0)),
        "comps.target.net_debt",
    )
    shares = number(
        target.get("shares", target.get("sharesOutstanding", target.get("shares_outstanding"))),
        "comps.target.shares",
    )
    if shares <= 0:
        raise ModelError("INPUT_INVALID", "comps.target.shares must be positive")
    selected = comps.get("multiples") or list(METRICS)
    if not isinstance(selected, list) or any(metric not in METRICS for metric in selected):
        raise ModelError("INPUT_INVALID", f"comps.multiples must be a subset of {list(METRICS)}")

    company = spec.get("company") or {}
    target_currency = str(target.get("currency") or company.get("currency") or "USD").upper()
    target_fye = target.get("fiscalYearEnd") or target.get("fiscal_year_end") or company.get("fiscalYearEnd") or "12-31"
    fx = comps.get("fx") if isinstance(comps.get("fx"), dict) else {}
    calendarize = bool(comps.get("calendarize", True))
    rows, excluded, warnings = _peer_rows(
        peers,
        target_currency=target_currency,
        target_fye=target_fye,
        fx=fx,
        calendarize=calendarize,
    )
    stats: dict[str, dict[str, Any]] = {}
    for metric in selected:
        values = [row["multiples"][metric] for row in rows if metric in row["multiples"]]
        stats[metric] = {
            "count": len(values),
            "min": min(values) if values else None,
            "p25": _percentile(values, 0.25),
            "median": _percentile(values, 0.5),
            "mean": mean(values) if values else None,
            "p75": _percentile(values, 0.75),
            "max": max(values) if values else None,
        }

    result = ModelResult(
        kind="comps",
        company=spec["company"]["name"],
        currency=spec["company"]["currency"],
        units=spec["company"]["units"],
        years=[str(peer.get("period") or "") for peer in peers],
        assumptions=comps,
        meta={
            "engine": "comps.v1", "stats": stats, "excluded": excluded,
            "validPeers": sum(1 for row in rows if row["multiples"]),
            "targetCurrency": target_currency, "calendarize": calendarize,
        },
    )
    result.warnings.extend(warnings)

    result.add_section(
        "Peer Multiples",
        columns=[
            "Peer", "Market cap", "Enterprise value", "EV/Revenue", "EV/EBITDA", "EV/EBIT",
            "P/E", "Period", "Source", "Currency", "FX", "Calendar factor", "Calendar method",
        ],
        rows=[
            {
                "label": row["name"],
                "values": [
                    row["name"], row["marketCap"], row["enterpriseValue"],
                    row["multiples"].get("ev_revenue"), row["multiples"].get("ev_ebitda"),
                    row["multiples"].get("ev_ebit"), row["multiples"].get("pe"),
                    row["period"], row["source"], row["currency"], row["fxRate"],
                    row["calendarizationFactor"], row["calendarizationMethod"],
                ],
                "kind": "calc",
            }
            for row in rows
        ],
    )
    result.add_section(
        "Multiple Statistics",
        columns=["Metric", "Peers", "Min", "25th", "Median", "Mean", "75th", "Max"],
        rows=[
            {
                "label": metric,
                "values": [metric, data["count"], data["min"], data["p25"], data["median"], data["mean"], data["p75"], data["max"]],
                "kind": "calc",
            }
            for metric, data in stats.items()
        ],
    )

    implied_rows = []
    for metric, data in stats.items():
        if not data["count"]:
            continue
        multiple_metric = metric.replace("ev_", "")
        for label, multiple in (("low", data["p25"]), ("median", data["median"]), ("high", data["p75"])):
            if multiple is None:
                continue
            if metric == "pe":
                implied_equity = multiple * target_value
                implied_ev = implied_equity + net_debt
            else:
                implied_ev = multiple * target_value
                implied_equity = implied_ev - net_debt
            implied_rows.append({
                "label": f"{metric} ({label})",
                "values": [metric, label, multiple, implied_ev, implied_equity, implied_equity / shares],
                "kind": "calc",
            })
    result.add_section(
        "Implied Valuation",
        columns=["Metric", "Basis", "Multiple", "Implied EV", "Implied equity", "Implied per share"],
        rows=implied_rows,
    )

    result.checks.append(Check("comps_peer_count",
                               "PASS" if len(rows) >= 3 else "WARN",
                               f"{len(rows)} comparable compan(ies) were usable; fewer than three is a weak sample",
                               value=float(len(rows))))
    result.checks.append(Check("comps_provenance",
                               "PASS" if not warnings else "WARN",
                               "every peer should state its period and source"))
    result.checks.append(Check("comps_exclusions_recorded", "PASS",
                               f"{len(excluded)} peer-metric combination(s) were excluded with a reason", value=float(len(excluded))))
    result.checks.append(Check("comps_target_shares", "PASS" if shares > 0 else "FAIL",
                               "target shares must be positive", value=shares))
    return result


__all__ = ["build_comps"]
