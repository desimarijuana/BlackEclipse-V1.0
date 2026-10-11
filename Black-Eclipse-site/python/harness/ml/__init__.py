"""Machine Learning Research Lab.

A deterministic, reproducible quantitative ML surface built on the SAME NumPy
core, persistence conventions and market-data path as the statistics, factor and
quant engines. It owns the full supervised-learning research workflow:

  * immutable, versioned datasets (built through the ONE market gateway),
  * point-in-time-aware target construction,
  * strictly chronological / walk-forward / purged cross-validation,
  * leakage-safe preprocessing and feature selection,
  * model adapters (pure-NumPy baselines + tree ensembles; optional scikit-learn
    / LightGBM / XGBoost when those wheels are installed),
  * evaluation, model artifacts with SHA-256 integrity, and lineage.

Design rules (see docs/ml-lab/ARCHITECTURE.md):

  * Never fabricate: a model family whose library is absent reports an honest
    `MODEL_UNAVAILABLE`; it is never silently replaced by a different model.
  * Every result is reproducible: dataset version, feature versions, split
    assignments, hyperparameters, dependency versions and seed travel with it.
  * Temporal correctness is a hard gate: features are only computed from data
    available at the prediction time, and the final test period is never used
    for model selection.
"""

from __future__ import annotations

from .models import ML_ENGINE_VERSION, MLError

__all__ = ["ML_ENGINE_VERSION", "MLError"]
