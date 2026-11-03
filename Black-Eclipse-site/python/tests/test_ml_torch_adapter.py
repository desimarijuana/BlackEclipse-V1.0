"""The optional deep-learning adapter (torch_mlp).

The point of these tests is the CONTRACT, not the library: when torch is absent
the family must report itself unavailable and fail honestly (never substitute),
and when it is present the adapter must train, serialize as plain JSON weights
and reload to identical predictions.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.ml import adapters
from harness.ml.models import MODEL_UNAVAILABLE, MLError

TORCH = adapters.optional_available("torch_mlp")
has_torch = TORCH[0]


def test_the_family_is_reported_with_its_real_availability() -> None:
    caps = {c["family"]: c for c in adapters.model_capabilities()}
    assert caps["torch_mlp"]["tier"] == "optional"
    assert caps["torch_mlp"]["available"] is has_torch
    if not has_torch:
        assert caps["torch_mlp"]["reason"]


@pytest.mark.skipif(has_torch, reason="torch IS installed; the absence path cannot be exercised")
def test_absent_torch_fails_honestly_and_never_substitutes() -> None:
    with pytest.raises(MLError) as exc:
        adapters.build_model("torch_mlp", "classification", {}, seed=1)
    assert getattr(exc.value, "code", None) == MODEL_UNAVAILABLE
    assert "torch" in str(exc.value)


@pytest.mark.skipif(not has_torch, reason="needs the optional torch install (python/requirements-train.txt)")
def test_torch_mlp_trains_and_round_trips_as_plain_json() -> None:
    rng = np.random.default_rng(0)
    X = rng.normal(size=(120, 3))
    y = (X[:, 0] + 0.5 * X[:, 1] > 0).astype(float)

    model = adapters.build_model("torch_mlp", "classification",
                                 {"hiddenSizes": [8], "epochs": 5, "batchSize": 32}, seed=3)
    model.fit(X, y)
    pred = model.predict(X)
    proba = model.predict_proba(X)
    assert proba is not None and proba.shape == (120, 2)
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-5)

    state = model.to_dict()
    assert state["family"] == "torch_mlp"
    assert isinstance(state["state"][0], list)          # JSON, not a pickle blob

    restored = adapters.load_model(state)
    assert restored.predict(X).tolist() == pred.tolist()
