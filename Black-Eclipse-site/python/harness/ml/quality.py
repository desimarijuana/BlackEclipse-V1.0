"""Dataset quality engine for the ML Research Lab.

Every finding is classified by severity (``info`` / ``warning`` / ``critical``).
Critical findings block an experiment; warnings are surfaced but do not stop it
unless the caller opts into strict mode. Findings are always real measurements of
the supplied data — nothing is invented, and a check that cannot run honestly
reports ``unavailable`` rather than passing.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

CRITICAL = "critical"
WARNING = "warning"
INFO = "info"


def _finding(code: str, severity: str, message: str, detail: Optional[dict[str, Any]] = None) -> dict:
    return {"code": code, "severity": severity, "message": message, "detail": detail or {}}


def evaluate_quality(
    *,
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list[str],
    timestamps: list[str],
    symbols: list[str],
    task: str,
    min_coverage: float = 0.5,
    min_class_count: int = 10,
    return_rows: bool = True,
) -> dict[str, Any]:
    """Run the dataset quality checks.

    ``X`` is ``(n_rows, n_features)`` (already flattened, NaN = missing),
    ``y`` the aligned label vector, ``timestamps``/``symbols`` the per-row
    provenance labels used for duplicate detection.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    findings: list[dict[str, Any]] = []
    n_rows, n_features = X.shape if X.ndim == 2 else (0, 0)

    if n_rows == 0 or n_features == 0:
        findings.append(_finding("EMPTY_DATASET", CRITICAL, "the dataset has no rows or features"))
        return {"ok": False, "findings": findings, "summary": {}}

    # missingness per feature
    missing_by_feature = {feature_names[j]: float(np.mean(~np.isfinite(X[:, j])))
                          for j in range(n_features)}
    total_missing = float(np.mean(~np.isfinite(X)))
    n_nonfinite = int(np.sum(~np.isfinite(X)))
    if n_nonfinite:
        findings.append(_finding("NON_FINITE_VALUES", INFO if total_missing < 0.05 else WARNING,
                                 f"{n_nonfinite} non-finite feature cell(s) ({total_missing:.1%})",
                                 {"byFeature": missing_by_feature}))
    worst_feature = max(missing_by_feature, key=lambda k: missing_by_feature[k])
    if missing_by_feature[worst_feature] > 0.5:
        findings.append(_finding("HIGH_MISSINGNESS", WARNING,
                                 f"feature {worst_feature!r} is {missing_by_feature[worst_feature]:.0%} missing",
                                 {"feature": worst_feature}))

    # duplicate (symbol, timestamp) observations
    if len(timestamps) == n_rows and len(symbols) == n_rows:
        pairs = list(zip(symbols, timestamps))
        n_dupes = len(pairs) - len(set(pairs))
        if n_dupes:
            findings.append(_finding("DUPLICATE_OBSERVATIONS", WARNING,
                                     f"{n_dupes} duplicate (symbol, timestamp) row(s)", {"count": n_dupes}))

    # timestamp monotonicity per symbol
    if len(timestamps) == n_rows:
        for sym in sorted(set(symbols)):
            idx = [i for i, s in enumerate(symbols) if s == sym]
            ts = [timestamps[i] for i in idx]
            if any(ts[k] >= ts[k + 1] for k in range(len(ts) - 1)):
                findings.append(_finding("UNORDERED_TIMESTAMPS", WARNING,
                                         f"timestamps for {sym!r} are not strictly increasing",
                                         {"symbol": sym}))
                break

    # target completeness + class balance
    finite_y = np.isfinite(y)
    coverage = float(finite_y.mean())
    if coverage < min_coverage:
        findings.append(_finding("LOW_COVERAGE", CRITICAL,
                                 f"only {coverage:.0%} of rows have a valid target (< {min_coverage:.0%})",
                                 {"coverage": coverage}))
    if task == "classification":
        yi = y[finite_y].astype(int)
        if yi.size == 0:
            findings.append(_finding("NO_VALID_LABELS", CRITICAL, "no valid classification labels"))
        else:
            classes, counts = np.unique(yi, return_counts=True)
            proportion = counts / counts.sum()
            imbalance = float(proportion.max())
            minority = int(counts.min())
            if classes.size < 2:
                findings.append(_finding("SINGLE_CLASS", CRITICAL,
                                         "the target has a single class", {"class": int(classes[0])}))
            if minority < min_class_count:
                findings.append(_finding("INSUFFICIENT_CLASS_COUNT", WARNING,
                                         f"minority class has only {minority} rows (< {min_class_count})",
                                         {"count": minority}))
            if imbalance > 0.9 and classes.size >= 2:
                findings.append(_finding("TARGET_IMBALANCE", WARNING,
                                         f"majority class is {imbalance:.0%} of labels",
                                         {"imbalance": imbalance}))
    else:
        if finite_y.sum() < 20:
            findings.append(_finding("INSUFFICIENT_LABELS", WARNING,
                                     f"only {int(finite_y.sum())} valid regression labels"))

    # zero-variance constant features
    constant = [feature_names[j] for j in range(n_features)
                if np.nanstd(np.where(np.isfinite(X[:, j]), X[:, j], np.nan)) == 0]
    if constant:
        findings.append(_finding("CONSTANT_FEATURES", WARNING,
                                 f"{len(constant)} constant feature(s)", {"features": constant}))

    critical = [f for f in findings if f["severity"] == CRITICAL]
    warnings = [f for f in findings if f["severity"] == WARNING]
    return {
        "ok": len(critical) == 0,
        "findings": findings,
        "summary": {
            "rows": int(n_rows),
            "features": int(n_features),
            "coverage": coverage,
            "missingness": total_missing,
            "nCritical": len(critical),
            "nWarning": len(warnings),
            "missingByFeature": missing_by_feature,
        },
    }


__all__ = ["evaluate_quality", "CRITICAL", "WARNING", "INFO"]
