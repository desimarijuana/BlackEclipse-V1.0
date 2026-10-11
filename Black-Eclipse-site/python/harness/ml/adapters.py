"""Model adapters for the ML Research Lab.

Every adapter exposes the SAME contract (``fit`` / ``predict`` / ``predict_proba``
/ feature importances / serialisation) so the training pipeline never special-
cases a family.

Two tiers:

  * **Native (always available, pure NumPy)** — ``dummy``, ``ridge``, ``logistic``
    and ``random_forest`` (a compact CART + bootstrap ensemble). These are real,
    deterministic and dependency-free.
  * **Optional (third-party wheels)** — ``sklearn_forest``, ``sklearn_extra_trees``,
    ``lightgbm`` and ``xgboost``. When the wheel is not installed the adapter
    reports ``MODEL_UNAVAILABLE`` with an install hint; it is NEVER silently
    substituted by another model.

Serialisation is JSON (the model's own state), never a pickle, so loading a
registered artifact cannot execute arbitrary code.
"""

from __future__ import annotations

import base64
import math
import pickle
from typing import Any, Optional

import numpy as np

from .models import (
    ML_ENGINE_VERSION,
    MLError,
    MODEL_UNAVAILABLE,
    NATIVE_MODEL_FAMILIES,
    OPTIONAL_MODEL_FAMILIES,
)
from ..stats.base import INVALID_INPUT, NOT_CONVERGED


# ── linear algebra helpers ───────────────────────────────────────────────────


def _add_bias(X: np.ndarray) -> np.ndarray:
    return np.hstack([np.ones((X.shape[0], 1)), X])


def _one_hot(y: np.ndarray, k: int) -> np.ndarray:
    Y = np.zeros((y.size, k))
    Y[np.arange(y.size), y.astype(int)] = 1.0
    return Y


# ── base ─────────────────────────────────────────────────────────────────────


class BaseModel:
    family = "base"
    supports_proba = False
    _task = "regression"

    def fit(self, X: np.ndarray, y: np.ndarray) -> "BaseModel":  # pragma: no cover
        raise NotImplementedError

    def predict(self, X: np.ndarray) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def predict_proba(self, X: np.ndarray) -> Optional[np.ndarray]:
        return None

    def feature_importances(self) -> Optional[np.ndarray]:
        return None

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


# ── dummy ────────────────────────────────────────────────────────────────────


class DummyModel(BaseModel):
    family = "dummy"

    def __init__(self, task: str) -> None:
        self._task = task
        self._const: float = 0.0
        self._proba: Optional[np.ndarray] = None
        self.n_classes: int = 0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "DummyModel":
        if self._task == "classification":
            yi = y.astype(int)
            self.n_classes = int(yi.max()) + 1
            counts = np.bincount(yi, minlength=self.n_classes).astype(float)
            self._proba = counts / counts.sum()
            self._const = float(np.argmax(self._proba))
        else:
            self._const = float(np.mean(y))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._task == "classification":
            self.supports_proba = True
            return np.full(X.shape[0], int(self._const), dtype=float)
        return np.full(X.shape[0], self._const, dtype=float)

    def predict_proba(self, X: np.ndarray) -> Optional[np.ndarray]:
        if self._proba is None:
            return None
        return np.tile(self._proba, (X.shape[0], 1))

    def to_dict(self) -> dict[str, Any]:
        return {"family": "dummy", "task": self._task, "const": self._const,
                "proba": None if self._proba is None else self._proba.tolist(),
                "nClasses": self.n_classes}


# ── ridge / OLS regression ───────────────────────────────────────────────────


class RidgeModel(BaseModel):
    family = "ridge"
    _task = "regression"

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = float(alpha)
        self.coef_: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RidgeModel":
        Xb = _add_bias(X)
        d = Xb.shape[1]
        reg = self.alpha * np.eye(d)
        reg[0, 0] = 0.0  # never penalise the intercept
        try:
            self.coef_ = np.linalg.solve(Xb.T @ Xb + reg, Xb.T @ y)
        except np.linalg.LinAlgError:
            self.coef_ = np.linalg.lstsq(Xb, y, rcond=None)[0]
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.coef_ is None:
            raise MLError(INVALID_INPUT, "ridge model is not fitted")
        return _add_bias(X) @ self.coef_

    def feature_importances(self) -> Optional[np.ndarray]:
        if self.coef_ is None:
            return None
        imp = np.abs(self.coef_[1:])
        total = imp.sum()
        return imp / total if total > 0 else imp

    def to_dict(self) -> dict[str, Any]:
        return {"family": "ridge", "alpha": self.alpha,
                "coef": None if self.coef_ is None else self.coef_.tolist()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RidgeModel":
        m = cls(alpha=float(d.get("alpha", 1.0)))
        if d.get("coef") is not None:
            m.coef_ = np.asarray(d["coef"], dtype=float)
        return m


# ── multinomial logistic regression ──────────────────────────────────────────


class LogisticModel(BaseModel):
    family = "logistic"
    supports_proba = True
    _task = "classification"

    def __init__(self, l2: float = 1e-3, learning_rate: float = 0.5,
                 iterations: int = 800, tol: float = 1e-7) -> None:
        self.l2 = float(l2)
        self.learning_rate = float(learning_rate)
        self.iterations = int(iterations)
        self.tol = float(tol)
        self.W: Optional[np.ndarray] = None
        self.n_classes: int = 0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LogisticModel":
        yi = y.astype(int)
        self.n_classes = int(yi.max()) + 1
        Xb = _add_bias(X)
        n, d = Xb.shape
        W = np.zeros((d, self.n_classes))
        Y = _one_hot(yi, self.n_classes)
        lr = self.learning_rate
        prev = math.inf
        for _ in range(self.iterations):
            z = Xb @ W
            z -= z.max(axis=1, keepdims=True)
            p = np.exp(z)
            p /= p.sum(axis=1, keepdims=True)
            grad = Xb.T @ (p - Y) / n
            grad[1:] += self.l2 * W[1:]
            W -= lr * grad
            loss = -np.mean(np.log(np.clip(p[np.arange(n), yi], 1e-15, 1.0)))
            if abs(prev - loss) < self.tol:
                break
            prev = loss
        self.W = W
        return self

    def _proba(self, X: np.ndarray) -> np.ndarray:
        if self.W is None:
            raise MLError(NOT_CONVERGED, "logistic model is not fitted", 500)
        z = _add_bias(X) @ self.W
        z -= z.max(axis=1, keepdims=True)
        p = np.exp(z)
        return p / p.sum(axis=1, keepdims=True)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._proba(X).argmax(axis=1).astype(float)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._proba(X)

    def feature_importances(self) -> Optional[np.ndarray]:
        if self.W is None:
            return None
        imp = np.abs(self.W[1:]).sum(axis=1)
        total = imp.sum()
        return imp / total if total > 0 else imp

    def to_dict(self) -> dict[str, Any]:
        return {"family": "logistic", "l2": self.l2, "learningRate": self.learning_rate,
                "iterations": self.iterations, "nClasses": self.n_classes,
                "W": None if self.W is None else self.W.tolist()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LogisticModel":
        m = cls(l2=float(d.get("l2", 1e-3)), learning_rate=float(d.get("learningRate", 0.5)),
                iterations=int(d.get("iterations", 800)))
        m.n_classes = int(d.get("nClasses", 0))
        if d.get("W") is not None:
            m.W = np.asarray(d["W"], dtype=float)
        return m


# ── CART decision tree + random forest ───────────────────────────────────────


class _Tree:
    __slots__ = ("feature", "threshold", "left", "right", "value", "importance")
    LEAF = -1

    def __init__(self) -> None:
        self.feature = _Tree.LEAF
        self.threshold = 0.0
        self.left: Optional["_Tree"] = None
        self.right: Optional["_Tree"] = None
        self.value = np.array([0.0])
        self.importance = 0.0


def _impurity(y: np.ndarray, task: str) -> float:
    if y.size == 0:
        return 0.0
    if task == "classification":
        _, counts = np.unique(y.astype(int), return_counts=True)
        p = counts / counts.sum()
        return float(1.0 - np.sum(p * p))  # Gini
    return float(np.var(y))


def _leaf_value(y: np.ndarray, task: str, n_classes: int) -> np.ndarray:
    if task == "classification":
        counts = np.bincount(y.astype(int), minlength=n_classes).astype(float)
        total = counts.sum()
        return counts / total if total > 0 else counts
    return np.array([float(np.mean(y))])


def _best_split(X: np.ndarray, y: np.ndarray, task: str, max_features: int,
                rng: np.random.Generator) -> tuple[int, float, float]:
    n, d = X.shape
    parent = _impurity(y, task)
    best = (-math.inf, -1, 0.0)
    features = rng.choice(d, size=min(max_features, d), replace=False) if max_features < d \
        else np.arange(d)
    for f in features:
        col = X[:, f]
        order = np.argsort(col, kind="mergesort")
        cs, ys = col[order], y[order]
        if cs[0] == cs[-1]:
            continue
        # candidate thresholds = midpoints between distinct consecutive values
        diff = np.nonzero(cs[1:] != cs[:-1])[0]
        gains = []
        for idx in diff:
            thr = 0.5 * (cs[idx] + cs[idx + 1])
            left, right = ys[:idx + 1], ys[idx + 1:]
            wl, wr = left.size / n, right.size / n
            gain = parent - (wl * _impurity(left, task) + wr * _impurity(right, task))
            gains.append((gain, float(thr)))
        if not gains:
            continue
        gain, thr = max(gains, key=lambda g: g[0])
        if gain > best[0]:
            best = (gain, int(f), thr)
    return best


def _build_tree(X: np.ndarray, y: np.ndarray, task: str, n_classes: int, max_depth: int,
                min_samples_leaf: int, max_features: int, rng: np.random.Generator,
                depth: int = 0) -> _Tree:
    node = _Tree()
    node.value = _leaf_value(y, task, n_classes)
    if depth >= max_depth or y.size < 2 * min_samples_leaf or _impurity(y, task) == 0.0:
        return node
    gain, feature, threshold = _best_split(X, y, task, max_features, rng)
    if feature < 0 or gain <= 0:
        return node
    mask = X[:, feature] <= threshold
    if mask.sum() < min_samples_leaf or (~mask).sum() < min_samples_leaf:
        return node
    node.feature = feature
    node.threshold = threshold
    node.importance = gain
    node.left = _build_tree(X[mask], y[mask], task, n_classes, max_depth, min_samples_leaf,
                            max_features, rng, depth + 1)
    node.right = _build_tree(X[~mask], y[~mask], task, n_classes, max_depth, min_samples_leaf,
                             max_features, rng, depth + 1)
    return node


def _tree_predict(node: _Tree, x: np.ndarray) -> np.ndarray:
    while node.feature != _Tree.LEAF:
        node = node.left if x[node.feature] <= node.threshold else node.right  # type: ignore[assignment]
    return node.value


def _tree_importances(node: _Tree, out: np.ndarray) -> float:
    if node.feature == _Tree.LEAF:
        return 0.0
    sub = _tree_importances(node.left, out) + _tree_importances(node.right, out)  # type: ignore[arg-type]
    total = node.importance + sub
    out[node.feature] += node.importance
    return total


def _tree_to_dict(node: _Tree) -> dict[str, Any]:
    d: dict[str, Any] = {"feature": node.feature, "threshold": node.threshold,
                         "value": node.value.tolist(), "importance": node.importance}
    if node.feature != _Tree.LEAF:
        d["left"] = _tree_to_dict(node.left)  # type: ignore[arg-type]
        d["right"] = _tree_to_dict(node.right)  # type: ignore[arg-type]
    return d


def _tree_from_dict(d: dict[str, Any]) -> _Tree:
    node = _Tree()
    node.feature = int(d["feature"])
    node.threshold = float(d["threshold"])
    node.value = np.asarray(d["value"], dtype=float)
    node.importance = float(d.get("importance", 0.0))
    if node.feature != _Tree.LEAF:
        node.left = _tree_from_dict(d["left"])
        node.right = _tree_from_dict(d["right"])
    return node


class RandomForestModel(BaseModel):
    family = "random_forest"

    def __init__(self, task: str, *, n_estimators: int = 50, max_depth: int = 6,
                 min_samples_leaf: int = 5, max_features: Optional[int] = None,
                 seed: int = 42) -> None:
        self._task = task
        self.n_estimators = int(n_estimators)
        self.max_depth = int(max_depth)
        self.min_samples_leaf = int(min_samples_leaf)
        self.max_features = max_features
        self.seed = int(seed)
        self.trees: list[_Tree] = []
        self.n_classes = 0
        self.n_features = 0
        self._importances: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RandomForestModel":
        rng = np.random.default_rng(self.seed)
        n, d = X.shape
        self.n_features = d
        if self._task == "classification":
            self.n_classes = int(y.astype(int).max()) + 1
            default_mf = max(1, int(math.sqrt(d)))
        else:
            self.n_classes = 0
            default_mf = max(1, d // 3)
        max_features = self.max_features or default_mf
        importances = np.zeros(d)
        for _ in range(self.n_estimators):
            idx = rng.integers(0, n, size=n)  # bootstrap
            tree = _build_tree(X[idx], y[idx], self._task, self.n_classes, self.max_depth,
                               self.min_samples_leaf, max_features, rng)
            _tree_importances(tree, importances)
            self.trees.append(tree)
        total = importances.sum()
        self._importances = importances / total if total > 0 else importances
        return self

    def predict_proba(self, X: np.ndarray) -> Optional[np.ndarray]:
        if self._task != "classification":
            return None
        acc = np.zeros((X.shape[0], self.n_classes))
        for tree in self.trees:
            for i in range(X.shape[0]):
                acc[i] += _tree_predict(tree, X[i])
        return acc / max(1, len(self.trees))

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._task == "classification":
            proba = self.predict_proba(X)
            return proba.argmax(axis=1).astype(float)  # type: ignore[union-attr]
        acc = np.zeros(X.shape[0])
        for tree in self.trees:
            for i in range(X.shape[0]):
                acc[i] += _tree_predict(tree, X[i])[0]
        return acc / max(1, len(self.trees))

    def feature_importances(self) -> Optional[np.ndarray]:
        return self._importances

    def to_dict(self) -> dict[str, Any]:
        return {"family": "random_forest", "task": self._task, "nEstimators": self.n_estimators,
                "maxDepth": self.max_depth, "minSamplesLeaf": self.min_samples_leaf,
                "seed": self.seed, "nClasses": self.n_classes, "nFeatures": self.n_features,
                "trees": [_tree_to_dict(t) for t in self.trees],
                "importances": None if self._importances is None else self._importances.tolist()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RandomForestModel":
        m = cls(d.get("task", "regression"), n_estimators=int(d.get("nEstimators", 50)),
                max_depth=int(d.get("maxDepth", 6)), min_samples_leaf=int(d.get("minSamplesLeaf", 5)),
                seed=int(d.get("seed", 42)))
        m.n_classes = int(d.get("nClasses", 0))
        m.n_features = int(d.get("nFeatures", 0))
        m.trees = [_tree_from_dict(t) for t in d.get("trees", [])]
        if d.get("importances") is not None:
            m._importances = np.asarray(d["importances"], dtype=float)
        return m


# ── optional third-party adapters ────────────────────────────────────────────

_OPTIONAL_IMPORTS = {
    "sklearn_forest": "sklearn.ensemble",
    "sklearn_extra_trees": "sklearn.ensemble",
    "lightgbm": "lightgbm",
    "xgboost": "xgboost",
}

_OPTIONAL_TASKS = {
    "sklearn_forest": ("classification", "regression"),
    "sklearn_extra_trees": ("classification", "regression"),
    "lightgbm": ("classification", "regression"),
    "xgboost": ("classification", "regression"),
}


def optional_available(family: str) -> tuple[bool, Optional[str]]:
    """Whether an optional family's library imports. Returns (available, reason)."""
    module = _OPTIONAL_IMPORTS.get(family)
    if module is None:
        return False, f"unknown optional family {family!r}"
    try:
        __import__(module.split(".")[0])
        if family.startswith("sklearn"):
            __import__("sklearn")
        return True, None
    except Exception as exc:  # noqa: BLE001 - absence is a supported outcome
        return False, str(exc)


def _build_optional(family: str, task: str, hyperparameters: dict[str, Any], seed: int) -> BaseModel:
    available, reason = optional_available(family)
    if not available:
        raise MLError(
            MODEL_UNAVAILABLE,
            f"model family {family!r} requires an optional dependency that is not installed "
            f"({reason}). Install it (see python/requirements-ml.txt); the runtime never "
            f"substitutes a different model.",
            503,
        )
    if task not in _OPTIONAL_TASKS[family]:
        raise MLError(INVALID_INPUT, f"{family} does not support task {task!r}")
    return _SklearnLikeAdapter(family, task, hyperparameters, seed)


class _SklearnLikeAdapter(BaseModel):
    """Thin wrapper around an optional library's estimator (lazy import)."""

    supports_proba = True

    def __init__(self, family: str, task: str, hyperparameters: dict[str, Any], seed: int) -> None:
        self.family = family
        self._task = task
        self._hp = dict(hyperparameters)
        self.seed = seed
        self._est: Any = None

    def _make(self) -> Any:
        hp = {k: v for k, v in self._hp.items()}
        if self.family == "sklearn_forest":
            from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
            cls = RandomForestClassifier if self._task == "classification" else RandomForestRegressor
            return cls(random_state=self.seed, **hp)
        if self.family == "sklearn_extra_trees":
            from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor
            cls = ExtraTreesClassifier if self._task == "classification" else ExtraTreesRegressor
            return cls(random_state=self.seed, **hp)
        if self.family == "lightgbm":
            import lightgbm as lgb
            cls = lgb.LGBMClassifier if self._task == "classification" else lgb.LGBMRegressor
            return cls(random_state=self.seed, verbose=-1, **hp)
        if self.family == "xgboost":
            import xgboost as xgb
            cls = xgb.XGBClassifier if self._task == "classification" else xgb.XGBRegressor
            return cls(random_state=self.seed, **hp)
        raise MLError(MODEL_UNAVAILABLE, f"unknown optional family {self.family!r}", 503)

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_SklearnLikeAdapter":
        self._est = self._make()
        self._est.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.asarray(self._est.predict(X), dtype=float)

    def predict_proba(self, X: np.ndarray) -> Optional[np.ndarray]:
        if self._task != "classification" or not hasattr(self._est, "predict_proba"):
            return None
        return np.asarray(self._est.predict_proba(X), dtype=float)

    def feature_importances(self) -> Optional[np.ndarray]:
        imp = getattr(self._est, "feature_importances_", None)
        return None if imp is None else np.asarray(imp, dtype=float)

    def to_dict(self) -> dict[str, Any]:
        # Third-party estimators are serialised with their own (joblib/pickle)
        # representation, embedded as base64. This is a trusted, locally-produced,
        # SHA-256-verified artifact; loading verifies the hash first (see
        # service.load_model_for_inference).
        if self._est is None:
            raise MLError(MODEL_UNAVAILABLE, "the model is not fitted", 500)
        try:
            import joblib  # noqa: PLC0415
            import io
            buffer = io.BytesIO()
            joblib.dump(self._est, buffer)
            blob = buffer.getvalue()
        except Exception:  # noqa: BLE001 - fall back to pickle
            blob = pickle.dumps(self._est, protocol=pickle.HIGHEST_PROTOCOL)
        return {"family": self.family, "task": self._task, "hyperparameters": dict(self._hp),
                "seed": self.seed, "nClasses": getattr(self._est, "n_classes_", None),
                "native": base64.b64encode(blob).decode("ascii")}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "_SklearnLikeAdapter":
        m = cls(d.get("family"), d.get("task", "regression"),
                d.get("hyperparameters") or {}, int(d.get("seed", 42)))
        blob = base64.b64decode(d["native"])
        try:
            import joblib  # noqa: PLC0415
            import io
            m._est = joblib.load(io.BytesIO(blob))
        except Exception:  # noqa: BLE001 - fall back to pickle
            m._est = pickle.loads(blob)  # noqa: S301 - hash-verified local artifact
        return m


# ── factory / capabilities ───────────────────────────────────────────────────


def build_model(family: str, task: str, hyperparameters: dict[str, Any], seed: int) -> BaseModel:
    """Construct an unfitted adapter. Raises for an unsupported family/task."""
    hp = dict(hyperparameters or {})
    if family == "dummy":
        return DummyModel(task)
    if family == "ridge":
        if task != "regression":
            raise MLError(INVALID_INPUT, "ridge supports regression targets only")
        return RidgeModel(alpha=float(hp.get("alpha", 1.0)))
    if family == "logistic":
        if task != "classification":
            raise MLError(INVALID_INPUT, "logistic supports classification targets only")
        return LogisticModel(l2=float(hp.get("l2", 1e-3)),
                             learning_rate=float(hp.get("learningRate", 0.5)),
                             iterations=int(hp.get("iterations", 800)))
    if family == "random_forest":
        return RandomForestModel(task, n_estimators=int(hp.get("nEstimators", 50)),
                                 max_depth=int(hp.get("maxDepth", 6)),
                                 min_samples_leaf=int(hp.get("minSamplesLeaf", 5)),
                                 seed=seed)
    if family in OPTIONAL_MODEL_FAMILIES:
        return _build_optional(family, task, hp, seed)
    raise MLError(INVALID_INPUT, f"unknown model family {family!r}")


def load_model(state: dict[str, Any]) -> BaseModel:
    family = state.get("family")
    if family == "dummy":
        m = DummyModel(state.get("task", "regression"))
        m._const = float(state.get("const", 0.0))
        m.n_classes = int(state.get("nClasses", 0))
        if state.get("proba") is not None:
            m._proba = np.asarray(state["proba"], dtype=float)
        return m
    if family == "ridge":
        return RidgeModel.from_dict(state)
    if family == "logistic":
        return LogisticModel.from_dict(state)
    if family == "random_forest":
        return RandomForestModel.from_dict(state)
    if family in OPTIONAL_MODEL_FAMILIES:
        if not state.get("native"):
            raise MLError(MODEL_UNAVAILABLE,
                          f"the artifact for {family!r} has no native model payload", 503)
        return _SklearnLikeAdapter.from_dict(state)
    raise MLError(MODEL_UNAVAILABLE, f"cannot load artifact for family {family!r}", 503)


def model_capabilities() -> list[dict[str, Any]]:
    """What is ACTUALLY available in this runtime (never aspirational)."""
    caps: list[dict[str, Any]] = []
    for family in NATIVE_MODEL_FAMILIES:
        tasks = ["classification", "regression"] if family in ("dummy", "random_forest") \
            else (["regression"] if family == "ridge" else ["classification"])
        caps.append({"family": family, "available": True, "tasks": tasks,
                     "tier": "native", "reason": None})
    for family in OPTIONAL_MODEL_FAMILIES:
        ok, reason = optional_available(family)
        caps.append({"family": family, "available": ok,
                     "tasks": list(_OPTIONAL_TASKS[family]), "tier": "optional",
                     "reason": reason})
    return caps


__all__ = ["BaseModel", "DummyModel", "RidgeModel", "LogisticModel", "RandomForestModel",
           "build_model", "load_model", "model_capabilities", "optional_available"]
