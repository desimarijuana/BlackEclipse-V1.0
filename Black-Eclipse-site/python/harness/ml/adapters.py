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
    # Optional deep learning (python/requirements-train.txt). Tabular MLP only.
    "torch_mlp": "torch",
}

_OPTIONAL_TASKS = {
    "sklearn_forest": ("classification", "regression"),
    "sklearn_extra_trees": ("classification", "regression"),
    "lightgbm": ("classification", "regression"),
    "xgboost": ("classification", "regression"),
    "torch_mlp": ("classification", "regression"),
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
    if family == "torch_mlp":
        return TorchMLPAdapter(task, hyperparameters, seed)
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


# ── optional deep learning (torch) ───────────────────────────────────────────


class TorchMLPAdapter(BaseModel):
    """A small fully-connected network on an optional `torch` install.

    Deliberately tabular only: this phase ships no image or sequence data path,
    so the adapter is an MLP rather than a CNN/RNN it could not honestly train.
    Weights are serialized as plain JSON floats (a few thousand of them), never
    pickled, so the artifact stays inspectable and hash-verified like every other
    ML artifact. Runs are seeded; floating-point training is reproducible on the
    same build, which is exactly what the artifact records.
    """

    family = "torch_mlp"
    supports_proba = True

    def __init__(self, task: str, hyperparameters: dict[str, Any], seed: int) -> None:
        self._task = task
        self._hp = dict(hyperparameters)
        self.seed = int(seed)
        self._net: Any = None
        self._n_features = 0
        self._n_classes = 0

    # ── construction ──
    def _hidden(self) -> list[int]:
        raw = self._hp.get("hiddenSizes") or [64, 32]
        return [max(1, int(h)) for h in raw]

    def _dropout(self) -> float:
        return min(0.9, max(0.0, float(self._hp.get("dropout", 0.0))))

    def _build_net(self, n_in: int, n_out: int) -> Any:
        import torch.nn as nn  # noqa: PLC0415

        layers: list[Any] = []
        prev = n_in
        for size in self._hidden():
            layers.append(nn.Linear(prev, size))
            layers.append(nn.ReLU())
            if self._dropout() > 0:
                layers.append(nn.Dropout(self._dropout()))
            prev = size
        layers.append(nn.Linear(prev, n_out))
        return nn.Sequential(*layers)

    # ── training / inference ──
    def fit(self, X: np.ndarray, y: np.ndarray) -> "TorchMLPAdapter":
        import torch  # noqa: PLC0415
        import torch.nn as nn  # noqa: PLC0415

        X = np.asarray(X, dtype=np.float32)
        if X.ndim != 2 or X.shape[0] == 0:
            raise MLError(INVALID_INPUT, "torch_mlp needs a non-empty 2-D feature matrix")
        torch.manual_seed(self.seed)
        rng = np.random.default_rng(self.seed)
        self._n_features = int(X.shape[1])

        classification = self._task == "classification"
        if classification:
            yi = np.asarray(y).astype(int)
            self._n_classes = int(yi.max()) + 1
            out_dim = self._n_classes
        else:
            yr = np.asarray(y, dtype=np.float32)
            out_dim = 1

        net = self._build_net(self._n_features, out_dim)
        loss_fn = nn.CrossEntropyLoss() if classification else nn.MSELoss()
        optimiser = torch.optim.Adam(net.parameters(), lr=float(self._hp.get("lr", 0.01)))
        epochs = max(1, int(self._hp.get("epochs", 60)))
        batch = max(1, int(self._hp.get("batchSize", 256)))
        n = X.shape[0]

        for _ in range(epochs):
            order = rng.permutation(n)
            for start in range(0, n, batch):
                idx = order[start:start + batch]
                xb = torch.as_tensor(X[idx])
                net.zero_grad()
                out = net(xb)
                if classification:
                    loss = loss_fn(out, torch.as_tensor(yi[idx], dtype=torch.long))
                else:
                    loss = loss_fn(out.view(-1), torch.as_tensor(yr[idx]))
                loss.backward()
                optimiser.step()

        self._net = net
        return self

    def _forward(self, X: np.ndarray) -> np.ndarray:
        import torch  # noqa: PLC0415

        if self._net is None:
            raise MLError(INVALID_INPUT, "torch_mlp model is not fitted")
        with torch.no_grad():
            out = self._net(torch.as_tensor(np.asarray(X, dtype=np.float32)))
        return out.cpu().numpy()

    def predict(self, X: np.ndarray) -> np.ndarray:
        out = self._forward(X)
        if self._task == "classification":
            return np.argmax(out, axis=1).astype(float)
        return np.asarray(out, dtype=float).reshape(-1)

    def predict_proba(self, X: np.ndarray) -> Optional[np.ndarray]:
        if self._task != "classification":
            return None
        out = self._forward(X)
        shifted = out - out.max(axis=1, keepdims=True)
        exp = np.exp(shifted)
        return exp / exp.sum(axis=1, keepdims=True)

    # ── persistence ──
    def to_dict(self) -> dict[str, Any]:
        if self._net is None:
            raise MLError(MODEL_UNAVAILABLE, "the model is not fitted", 500)
        state = self._net.state_dict()
        return {
            "family": "torch_mlp", "task": self._task,
            "hyperparameters": dict(self._hp), "seed": self.seed,
            "nFeatures": self._n_features, "nClasses": self._n_classes,
            "stateKeys": list(state.keys()),
            "state": [t.detach().cpu().numpy().tolist() for t in state.values()],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TorchMLPAdapter":
        import torch  # noqa: PLC0415

        m = cls(d.get("task", "regression"), d.get("hyperparameters") or {},
                int(d.get("seed", 42)))
        available, reason = optional_available("torch_mlp")
        if not available:
            raise MLError(MODEL_UNAVAILABLE,
                          f"loading this artifact needs torch, which is not installed ({reason})",
                          503)
        m._n_features = int(d.get("nFeatures", 0))
        m._n_classes = int(d.get("nClasses", 0))
        out_dim = m._n_classes if m._task == "classification" else 1
        net = m._build_net(m._n_features, out_dim)
        keys = list(d.get("stateKeys") or [])
        values = d.get("state") or []
        if len(keys) != len(values):
            raise MLError("REPRODUCIBILITY_MISMATCH",
                          "the artifact's weight list does not match its key list", 409)
        net.load_state_dict({k: torch.as_tensor(v) for k, v in zip(keys, values)})
        m._net = net
        return m


# ── clustering / anomaly ─────────────────────────────────────────────────────


class KMeansModel(BaseModel):
    """Lloyd's k-means with a deterministic k-means++ initialisation.

    No label is used: `fit(X, y)` ignores `y` entirely (a clustering dataset has
    none), which is why the pipeline passes a placeholder. Determinism comes from
    the seeded RNG — the same data and seed give the same centroids, so a run is
    reproducible.
    """

    family = "kmeans"
    _task = "clustering"

    def __init__(self, n_clusters: int = 4, max_iter: int = 100,
                 tol: float = 1e-6, seed: int = 0) -> None:
        self.n_clusters = max(2, int(n_clusters))
        self.max_iter = max(1, int(max_iter))
        self.tol = float(tol)
        self.seed = int(seed)
        self.centers_: Optional[np.ndarray] = None
        self.inertia_: Optional[float] = None

    def _init_centers(self, X: np.ndarray) -> np.ndarray:
        rng = np.random.default_rng(self.seed)
        n = X.shape[0]
        k = min(self.n_clusters, n)
        centers = np.empty((k, X.shape[1]), dtype=float)
        centers[0] = X[rng.integers(n)]
        closest = ((X - centers[0]) ** 2).sum(axis=1)
        for i in range(1, k):
            total = float(closest.sum())
            if total <= 0:
                centers[i] = X[rng.integers(n)]
            else:
                probs = closest / total
                centers[i] = X[rng.choice(n, p=probs)]
            closest = np.minimum(closest, ((X - centers[i]) ** 2).sum(axis=1))
        return centers

    def _nearest(self, X: np.ndarray) -> np.ndarray:
        """Cluster index of each row, in bounded chunks (never an (n, k, d) cube)."""
        centers = self.centers_
        if centers is None:
            raise MLError(INVALID_INPUT, "kmeans model is not fitted")
        out = np.empty(X.shape[0], dtype=int)
        step = 20_000
        for start in range(0, X.shape[0], step):
            block = X[start:start + step]
            d = ((block[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
            out[start:start + step] = np.argmin(d, axis=1)
        return out

    def fit(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> "KMeansModel":
        X = np.asarray(X, dtype=float)
        if X.ndim != 2 or X.shape[0] == 0:
            raise MLError(INVALID_INPUT, "kmeans needs a non-empty 2-D feature matrix")
        centers = self._init_centers(X)
        self.centers_ = centers
        labels = self._nearest(X)
        for _ in range(self.max_iter):
            moved = 0.0
            for i in range(centers.shape[0]):
                rows = X[labels == i]
                if rows.size:
                    new = rows.mean(axis=0)
                    moved = max(moved, float(np.abs(new - centers[i]).max()))
                    centers[i] = new
            self.centers_ = centers
            new_labels = self._nearest(X)
            converged = moved <= self.tol or np.array_equal(new_labels, labels)
            labels = new_labels
            if converged:
                break
        self.inertia_ = float(((X - centers[labels]) ** 2).sum())
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._nearest(np.asarray(X, dtype=float)).astype(float)

    def to_dict(self) -> dict[str, Any]:
        if self.centers_ is None:
            raise MLError(INVALID_INPUT, "kmeans model is not fitted")
        return {"family": "kmeans", "task": self._task, "nClusters": int(self.centers_.shape[0]),
                "centers": self.centers_.tolist(), "inertia": self.inertia_,
                "maxIter": self.max_iter, "tol": self.tol, "seed": self.seed}

    @classmethod
    def from_dict(cls, state: dict[str, Any]) -> "KMeansModel":
        m = cls(n_clusters=int(state.get("nClusters", 2)),
                max_iter=int(state.get("maxIter", 100)),
                tol=float(state.get("tol", 1e-6)), seed=int(state.get("seed", 0)))
        m.centers_ = np.asarray(state.get("centers"), dtype=float)
        m.inertia_ = state.get("inertia")
        return m


class MadAnomalyModel(BaseModel):
    """Robust per-feature outlier score (median / MAD), flagged at a quantile.

    The score of a row is the largest standardized distance from the training
    medians; the flag threshold is the ``1 - contamination`` quantile of the
    TRAINING scores. Fitting only sees training rows, so the reported rate on a
    later fold is a real out-of-sample rate and not the rate it was tuned to.
    """

    family = "mad_z"
    _task = "anomaly"

    def __init__(self, contamination: float = 0.05) -> None:
        self.contamination = min(1.0, max(0.0, float(contamination)))
        self.median_: Optional[np.ndarray] = None
        self.scale_: Optional[np.ndarray] = None
        self.threshold_: Optional[float] = None

    def score(self, X: np.ndarray) -> np.ndarray:
        if self.median_ is None or self.scale_ is None:
            raise MLError(INVALID_INPUT, "anomaly model is not fitted")
        X = np.asarray(X, dtype=float)
        return np.max(np.abs(X - self.median_) / self.scale_, axis=1)

    def fit(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> "MadAnomalyModel":
        X = np.asarray(X, dtype=float)
        if X.ndim != 2 or X.shape[0] < 2:
            raise MLError(INVALID_INPUT, "an anomaly model needs at least two rows")
        self.median_ = np.median(X, axis=0)
        mad = np.median(np.abs(X - self.median_), axis=0) * 1.4826
        std = np.std(X, axis=0, ddof=1)
        # A constant column carries no signal: scale 1 keeps it from exploding.
        self.scale_ = np.where(mad > 0, mad, np.where(std > 0, std, 1.0))
        scores = self.score(X)
        self.threshold_ = float(np.quantile(scores, 1.0 - self.contamination)) \
            if self.contamination > 0 else float(np.max(scores))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.threshold_ is None:
            raise MLError(INVALID_INPUT, "anomaly model is not fitted")
        return (self.score(X) > self.threshold_).astype(float)

    def to_dict(self) -> dict[str, Any]:
        if self.median_ is None or self.scale_ is None:
            raise MLError(INVALID_INPUT, "anomaly model is not fitted")
        return {"family": "mad_z", "task": self._task, "median": self.median_.tolist(),
                "scale": self.scale_.tolist(), "threshold": self.threshold_,
                "contamination": self.contamination}

    @classmethod
    def from_dict(cls, state: dict[str, Any]) -> "MadAnomalyModel":
        m = cls(contamination=float(state.get("contamination", 0.05)))
        m.median_ = np.asarray(state.get("median"), dtype=float)
        m.scale_ = np.asarray(state.get("scale"), dtype=float)
        m.threshold_ = state.get("threshold")
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
    if family == "kmeans":
        if task != "clustering":
            raise MLError(INVALID_INPUT, "kmeans supports clustering only")
        return KMeansModel(n_clusters=int(hp.get("nClusters", 4)),
                           max_iter=int(hp.get("maxIter", 100)),
                           tol=float(hp.get("tol", 1e-6)), seed=seed)
    if family == "mad_z":
        if task != "anomaly":
            raise MLError(INVALID_INPUT, "mad_z supports anomaly detection only")
        return MadAnomalyModel(contamination=float(hp.get("contamination", 0.05)))
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
    if family == "kmeans":
        return KMeansModel.from_dict(state)
    if family == "mad_z":
        return MadAnomalyModel.from_dict(state)
    if family == "torch_mlp":
        return TorchMLPAdapter.from_dict(state)
    if family in OPTIONAL_MODEL_FAMILIES:
        if not state.get("native"):
            raise MLError(MODEL_UNAVAILABLE,
                          f"the artifact for {family!r} has no native model payload", 503)
        return _SklearnLikeAdapter.from_dict(state)
    raise MLError(MODEL_UNAVAILABLE, f"cannot load artifact for family {family!r}", 503)


def model_capabilities() -> list[dict[str, Any]]:
    """What is ACTUALLY available in this runtime (never aspirational)."""
    caps: list[dict[str, Any]] = []
    _native_tasks = {
        "dummy": ["classification", "regression"],
        "ridge": ["regression"],
        "logistic": ["classification"],
        "random_forest": ["classification", "regression"],
        "kmeans": ["clustering"],
        "mad_z": ["anomaly"],
    }
    for family in NATIVE_MODEL_FAMILIES:
        caps.append({"family": family, "available": True, "tasks": _native_tasks[family],
                     "tier": "native", "reason": None})
    for family in OPTIONAL_MODEL_FAMILIES:
        ok, reason = optional_available(family)
        caps.append({"family": family, "available": ok,
                     "tasks": list(_OPTIONAL_TASKS[family]), "tier": "optional",
                     "reason": reason})
    return caps


__all__ = ["BaseModel", "DummyModel", "RidgeModel", "LogisticModel", "RandomForestModel",
           "KMeansModel", "MadAnomalyModel", "TorchMLPAdapter",
           "build_model", "load_model", "model_capabilities", "optional_available"]
