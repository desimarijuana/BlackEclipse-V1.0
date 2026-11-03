"""Ensembles over already-registered models — a composition, not a new trainer.

An ensemble is a rule applied to the predictions of models that already exist. It
never re-fits anything, which is what makes it cheap and auditable: the members,
their versions and the rule are the whole artifact.

Rules:

  * **same folds or nothing.** Members must have been validated on the same rows;
    their out-of-fold row indices are intersected and an empty intersection is an
    error, because averaging predictions from different test rows would compare
    apples to oranges;
  * **classification needs a tie-break.** Probabilities are averaged and the argmax
    decides; when a member exposes no probabilities it is a majority vote, with
    ties going to the lowest class code (stated, deterministic);
  * no metric is invented — the blend's metrics are computed on the members' own
    out-of-fold outcomes.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .models import MLError

MAX_MEMBERS = 8


def blend(
    task: str,
    predictions: list[list[float]],
    probabilities: Optional[list[Optional[list[list[float]]]]] = None,
) -> dict[str, Any]:
    """Combine member predictions (and probabilities) into one prediction set."""
    if not predictions:
        raise MLError("INVALID_INPUT", "an ensemble needs at least one member", 422)
    width = len(predictions[0])
    if any(len(p) != width for p in predictions):
        raise MLError("INVALID_INPUT", "members produced different numbers of predictions", 422)

    if task == "regression":
        mean = np.mean(np.asarray(predictions, dtype=float), axis=0)
        return {"pred": [float(v) for v in mean], "proba": None}

    probas = probabilities or []
    if probas and all(p is not None for p in probas) and len(probas) == len(predictions):
        stacked = np.asarray(probas, dtype=float)          # (members, rows, classes)
        averaged = stacked.mean(axis=0)
        return {"pred": [float(v) for v in np.argmax(averaged, axis=1)],
                "proba": averaged.tolist()}

    # Majority vote; a tie resolves to the lowest class code (deterministic).
    votes = np.asarray(predictions, dtype=float)
    out: list[float] = []
    for row in range(width):
        values, counts = np.unique(votes[:, row], return_counts=True)
        best = values[counts == counts.max()]
        out.append(float(best.min()))
    return {"pred": out, "proba": None}


def align_out_of_fold(members: list[dict[str, Any]]) -> tuple[list[int], list[list[float]], Optional[list[Optional[list[list[float]]]]]]:
    """Align members' out-of-fold predictions on their shared row indices.

    Each member is ``{rowIndex, pred, proba?}``. The order follows the FIRST
    member's rows; a member missing a row is an error rather than an implicit zero.
    """
    if not members:
        raise MLError("INVALID_INPUT", "an ensemble needs at least one member", 422)
    shared = set(int(i) for i in members[0]["rowIndex"])
    for member in members[1:]:
        shared &= set(int(i) for i in member["rowIndex"])
    if not shared:
        raise MLError("INVALID_INPUT",
                      "the members share no out-of-fold rows — they were validated on "
                      "different folds, so their predictions are not comparable", 422)

    order = [int(i) for i in members[0]["rowIndex"] if int(i) in shared]
    positions = [{int(r): pos for pos, r in enumerate(member["rowIndex"])} for member in members]
    predictions = [[float(member["pred"][positions[m][row]]) for row in order]
                   for m, member in enumerate(members)]
    probas: Optional[list[Optional[list[list[float]]]]] = []
    for m, member in enumerate(members):
        if member.get("proba") is None:
            probas.append(None)
        else:
            probas.append([member["proba"][positions[m][row]] for row in order])
    return order, predictions, probas


__all__ = ["MAX_MEMBERS", "align_out_of_fold", "blend"]
