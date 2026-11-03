"""Deterministic model-recipe planner for the ML Research Lab.

A *recipe* is the bridge between "build me a model that predicts X" and the
existing experiment pipeline: a concrete family, hyperparameters, split design
and feature-selection choice for a specific data profile, each with the reason it
was chosen.

Rules that make it safe to expose to an agent:

  * **Deterministic.** Same profile + preference ⇒ same plan. No model, no
    randomness, no network.
  * **Never plans something unavailable.** The family is chosen from the
    families the runtime reports as actually importable, so a plan cannot ask
    for a library the machine does not have.
  * **Planning is not training.** A plan carries no metric — it is a proposal
    until the caller runs it.
  * **Explainable.** Every choice appends a human rationale line, and genuine
    risks (a tiny sample) are warnings on the plan rather than silent caveats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .models import MLError, SplitSpec


PREFERENCES = ("balanced", "interpretable", "accurate", "deep")


@dataclass
class DataProfile:
    """What the planner needs to know about the data (never the data itself)."""

    rows: int
    features: int
    task: str = "classification"
    time_ordered: bool = True
    class_count: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {"rows": int(self.rows), "features": int(self.features),
                "task": self.task, "timeOrdered": bool(self.time_ordered),
                "classCount": self.class_count}


@dataclass
class RecipePlan:
    task: str
    model_family: str
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    split: SplitSpec = field(default_factory=SplitSpec)
    selection: dict[str, Any] = field(default_factory=lambda: {"method": "none"})
    scale: bool = True
    rationale: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task, "modelFamily": self.model_family,
            "hyperparameters": dict(self.hyperparameters), "split": self.split.to_dict(),
            "selection": dict(self.selection), "scale": self.scale,
            "rationale": list(self.rationale), "warnings": list(self.warnings),
        }


def profile_from_manifest(manifest: dict[str, Any]) -> DataProfile:
    """A profile from a built dataset version's manifest (no rows are loaded)."""
    target = manifest.get("target") or {}
    task = str(target.get("task") or "")
    if not task:
        raise MLError("INVALID_INPUT", "the dataset manifest does not declare a task", 422)
    class_count = target.get("nClasses")
    return DataProfile(
        rows=int(manifest.get("rows") or 0),
        features=len(manifest.get("featureNames") or []),
        task=task,
        # A records dataset with an explicit time column is ordered; row order is
        # always chronological in this engine, so this stays true either way.
        time_ordered=True,
        class_count=int(class_count) if isinstance(class_count, (int, float)) and class_count else None,
    )


def available_families() -> dict[str, bool]:
    """Family → actually importable, straight from the engine's own report."""
    from .adapters import model_capabilities  # noqa: PLC0415

    return {cap["family"]: bool(cap["available"]) for cap in model_capabilities()}


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def plan_recipe(
    profile: DataProfile,
    *,
    preference: str = "balanced",
    available: Optional[dict[str, bool]] = None,
) -> RecipePlan:
    """Choose a recipe for a data profile. Pure and deterministic."""
    if preference not in PREFERENCES:
        raise MLError("INVALID_INPUT",
                      f"unknown preference {preference!r} (one of {', '.join(PREFERENCES)})", 422)
    if profile.rows < 10:
        raise MLError("INSUFFICIENT_DATA",
                      f"{profile.rows} row(s) is not enough to train and validate a model", 422)
    if profile.features < 1:
        raise MLError("INVALID_INPUT", "a model needs at least one feature", 422)
    task = profile.task
    if task not in ("classification", "regression", "clustering", "anomaly"):
        raise MLError("INVALID_INPUT", f"unsupported task {task!r}", 422)

    avail = dict(available) if available is not None else available_families()
    plan = RecipePlan(task=task, model_family="", split=SplitSpec())

    # ── validation design (identical policy for every family) ────────────────
    plan.split = SplitSpec(
        method="walk_forward",
        n_splits=5 if profile.rows >= 500 else 3,
        test_size=0,
        window=0,
        window_mode="expanding",
        purge=True,
        embargo=1 if profile.time_ordered else 0,
    )
    plan.rationale.append(
        f"walk-forward {plan.split.n_splits}-fold validation with purging"
        + (" and a 1-row embargo" if plan.split.embargo else "")
        + " — the engine never shuffles time-ordered rows")

    if profile.rows < 200:
        plan.warnings.append(
            f"only {profile.rows} rows: fold metrics will be noisy, and a held-out "
            "period is small. Collect more rows before trusting the result.")

    # ── unsupervised tasks ──────────────────────────────────────────────────
    if task == "clustering":
        k = _clamp(int(round((profile.rows / 2) ** 0.5)), 2, 8)
        plan.model_family = "kmeans"
        plan.hyperparameters = {"nClusters": k}
        plan.rationale.append(
            f"k-means with {k} clusters: a deterministic partition of {profile.features} "
            "features; tune nClusters after seeing the silhouette")
        return plan

    if task == "anomaly":
        plan.model_family = "mad_z"
        plan.hyperparameters = {"contamination": 0.05}
        plan.rationale.append(
            "median/MAD outlier score at a 5% contamination threshold: robust to a "
            "skewed feature and needs no labels")
        plan.warnings.append(
            "anomaly detection has no ground truth here — the run reports a flag rate "
            "and score distribution, not an accuracy")
        return plan

    # ── supervised selection ────────────────────────────────────────────────
    def _pick(*names: str) -> Optional[str]:
        for name in names:
            if avail.get(name):
                return name
        return None

    family: Optional[str]
    if preference == "deep":
        family = _pick("torch_mlp")
        if family:
            plan.rationale.append("requested deep model: a seeded tabular MLP (torch)")
        else:
            plan.warnings.append(
                "torch is not installed, so the deep model cannot be planned; "
                "install python/requirements-train.txt to enable torch_mlp")
    elif preference == "interpretable":
        family = _pick("ridge" if task == "regression" else "logistic")
    elif preference == "accurate" or profile.rows >= 2_000:
        family = _pick("lightgbm", "xgboost", "sklearn_forest", "random_forest")
    else:
        family = _pick("ridge" if task == "regression" else "logistic")

    if family is None:
        family = _pick("random_forest", "ridge", "logistic")
    if family is None:
        raise MLError("MODEL_UNAVAILABLE",
                      "no model family is available in this runtime for the requested task", 503)

    plan.model_family = family
    if family in ("logistic", "ridge"):
        plan.hyperparameters = ({"l2": 1e-3} if family == "logistic" else {"alpha": 1.0})
        plan.rationale.append(
            f"{family}: a regularised linear model trains in a second and is "
            "interpretable — the right default for a small sample")
        plan.scale = True
    elif family in ("lightgbm", "xgboost", "sklearn_forest"):
        plan.hyperparameters = {}
        plan.rationale.append(
            f"{family}: gradient-boosted/ensemble trees capture non-linear feature "
            "interactions without hand-built transforms")
    elif family == "random_forest":
        plan.hyperparameters = {"nEstimators": 200 if profile.rows >= 2_000 else 100,
                                "maxDepth": 6, "minSamplesLeaf": 5}
        plan.rationale.append(
            "random_forest: the native tree ensemble (no optional wheel needed), "
            "which tolerates mixed feature scales")
    elif family == "torch_mlp":
        plan.hyperparameters = {"hiddenSizes": [64, 32], "epochs": 60, "lr": 0.01,
                                "batchSize": 256, "dropout": 0.1}
        plan.rationale.append(
            "torch_mlp: a small seeded network for tabular data; no image/sequence "
            "adapter is claimed")
    else:
        plan.hyperparameters = {}

    # Feature selection needs a label, which supervised tasks have.
    if profile.features > 40:
        plan.selection = {"method": "correlation", "topK": 20}
        plan.rationale.append(
            f"{profile.features} features: keep the 20 most correlated with the label, "
            "fitted on each training fold only")
    else:
        plan.selection = {"method": "none"}
        plan.rationale.append("feature count is small, so no selection step is added")

    return plan


def to_experiment_payload(
    plan: RecipePlan,
    *,
    dataset_id: str,
    dataset_version: str,
    title: Optional[str] = None,
    seed: int = 42,
) -> dict[str, Any]:
    """The exact `/ml/v1/experiments` body that executes the plan."""
    return {
        "datasetId": dataset_id,
        "datasetVersion": dataset_version,
        "title": title or f"{plan.task}-{plan.model_family}",
        "modelFamily": plan.model_family,
        "hyperparameters": dict(plan.hyperparameters),
        "selection": dict(plan.selection),
        "split": plan.split.to_dict(),
        "seed": int(seed),
        "scale": plan.scale,
        "task": plan.task,
    }


__all__ = [
    "PREFERENCES",
    "DataProfile",
    "RecipePlan",
    "available_families",
    "plan_recipe",
    "profile_from_manifest",
    "to_experiment_payload",
]
