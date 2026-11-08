"""Trade learning — mistake → lesson → recurrence → bounded playbook improvement.

The package owns the *trading domain* of learning, not a second learning system:

* detection is deterministic (`detectors.py`);
* recurrence is the ONE `LearningRecurrence` ledger (`store.py`);
* proposals are inert until an explicit commit (`climb.py`, `store.py`);
* the only behaviour the loop may change is the playbook envelope, and only
  toward tighter risk (`playbook.py`);
* evaluation is out-of-sample over recorded trades (`replay.py`).

It imports no broker code and never places, modifies or cancels an order.
"""

from __future__ import annotations

from .climb import climb
from .detectors import review, signature_for
from .model import DEFAULT_LIMITS, Finding, KNOBS, Playbook, Trade, parse_trades
from .playbook import (
    PlaybookRefused,
    candidate_limits,
    is_tighter,
    mutable_knobs,
    validate_limits,
)
from .replay import decide, evaluate, walk_forward
from .service import TradeLearningService
from .store import TradeLearningStore

__all__ = [
    "DEFAULT_LIMITS",
    "Finding",
    "KNOBS",
    "Playbook",
    "PlaybookRefused",
    "Trade",
    "TradeLearningService",
    "TradeLearningStore",
    "candidate_limits",
    "climb",
    "decide",
    "evaluate",
    "is_tighter",
    "mutable_knobs",
    "parse_trades",
    "review",
    "signature_for",
    "validate_limits",
    "walk_forward",
]
