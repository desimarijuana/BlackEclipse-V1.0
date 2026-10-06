"""The File System subsystem for the code capability.

A unified filesystem service layered under the existing code tools:

    Agent runtime  →  Tool registry  →  fs tools (tools.py)
                                            ↓
                                    FileSystemService (service.py)
                                            ↓
    core        errors · permissions · resolver (+ existing policy/workspace)
    operations  list/read/write/create/delete/move/copy/rename/mkdir/rmdir
    search      search_text/search_files/find_files (ripgrep + fallback)
    symbols     search_symbols/find_references (ast + regex)
    editing     patch_file/replace_text/insert_text/delete_text/apply_diff
    metadata    file_metadata/file_hash/file_permissions
    transactions / diff / index / watch

The core stays deterministic and LLM-free: the model decides WHAT to change; this
package decides HOW to do it safely. Path safety is NOT re-implemented here — it
delegates to `code/policy.py` and `code/workspace.py`, the existing authorities.
"""

from .context import FsContext
from .errors import ALL_CODES, FsError
from .service import FileSystemService, build_service

__all__ = ["ALL_CODES", "FsContext", "FileSystemService", "FsError", "build_service"]
