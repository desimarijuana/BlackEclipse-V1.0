"""Eclipse-Memory — dedicated persistence for memory, skills, learning.

This package owns **`eclipse-memory.db`**, a SQLite database separate from:
  * `jdds.db`            — market data + Trading Journal (Prisma);
  * `agent-memory.db`    — harness run/event/tool traces.

It is the single control layer for agent memory, user preferences, episodic /
semantic / procedural memory, corrections, mistakes, skills, skill versions,
learning candidates, evaluations and promotion history. There is exactly one
access path: `EclipseMemoryStore` (raw persistence) wrapped by
`EclipseMemoryService` (the write/retrieve pipelines). No component may open
its own connection to `eclipse-memory.db`.

Database resolution (see `config.py`):
    ECLIPSE_MEMORY_DB_PATH  → explicit path (test isolation uses this)
    else <repo root>/eclipse-memory.db  (the repo containing `python/`, NOT the
         process working directory — so every launch resolves the same store).
"""

from .config import default_db_path, db_filename, memory_db_path
from .db import EclipseMemoryDb
from .store import EclipseMemoryStore
from .service import EclipseMemoryService
from .retrieval import RetrievalDiagnostics, RetrievalResult

__all__ = [
    "EclipseMemoryDb",
    "EclipseMemoryService",
    "EclipseMemoryStore",
    "RetrievalDiagnostics",
    "RetrievalResult",
    "db_filename",
    "default_db_path",
    "memory_db_path",
]
