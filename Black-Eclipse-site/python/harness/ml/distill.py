"""Distillation corpus — a dataset version as instruction/answer JSONL.

This is the honest, runnable half of the generative path: it turns a trained
dataset's rows into chat-format examples that a fine-tune can consume, without
pretending to train anything here.

What it is: **behaviour distillation** of a decision the dataset already encodes
(features → label). It is not general instruction data, and the corpus says so on
every build. Rows whose features or label are missing are skipped, never filled.

The companion trainer (`ml.llm`) is opt-in: without torch/transformers/peft the
runtime reports MODEL_UNAVAILABLE and still writes the corpus + a runnable recipe
so the fine-tune can happen elsewhere.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

import numpy as np

MAX_EXAMPLES = 20_000


def _answer(value: float, labels: list[str]) -> Optional[str]:
    if not np.isfinite(value):
        return None
    if labels and 0 <= int(value) < len(labels):
        return str(labels[int(value)])
    return f"{float(value):.6g}"


def build_examples(arrays: dict[str, Any], manifest: dict[str, Any], *,
                   limit: int = MAX_EXAMPLES) -> list[dict[str, Any]]:
    """One instruction/answer pair per complete row, in dataset order."""
    names = list(arrays.get("featureNames") or manifest.get("featureNames") or [])
    X = np.asarray(arrays["X"], dtype=float)
    y = np.asarray(arrays["y"], dtype=float)
    target = manifest.get("target") or {}
    target_name = str(target.get("column") or "target")
    labels = list(target.get("classLabels") or [])
    task = str(target.get("task") or "regression")

    take = max(0, min(int(limit), int(X.shape[0])))
    examples: list[dict[str, Any]] = []
    for row in range(take):
        if not np.isfinite(X[row]).all():
            continue
        answer = _answer(y[row], labels)
        if answer is None:
            continue
        listing = "\n".join(f"- {name}: {float(X[row, i]):.6g}"
                            for i, name in enumerate(names))
        prompt = (f"Predict `{target_name}` from these features.\n{listing}")
        examples.append({
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": answer},
            ],
            "meta": {"row": row, "task": task},
        })
    return examples


def to_jsonl(examples: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(item, sort_keys=True) for item in examples)


def corpus_hash(examples: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in examples:
        digest.update(json.dumps(item, sort_keys=True).encode())
    return digest.hexdigest()


__all__ = ["MAX_EXAMPLES", "build_examples", "corpus_hash", "to_jsonl"]
