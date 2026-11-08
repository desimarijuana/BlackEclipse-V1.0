"""Shared limits for the in-editor graph assistant.

Kept in one tiny module so the tool loop and the working-copy session cannot
drift on the bounds the product promises.
"""

MAX_TOOL_ROUNDS = 12
MAX_ASSIST_OPS = 30
MAX_ASSIST_NODES = 120
MAX_ASSIST_RUNS = 2
MAX_CATALOG_RESULTS = 10

__all__ = [
    "MAX_TOOL_ROUNDS",
    "MAX_ASSIST_OPS",
    "MAX_ASSIST_NODES",
    "MAX_ASSIST_RUNS",
    "MAX_CATALOG_RESULTS",
]
