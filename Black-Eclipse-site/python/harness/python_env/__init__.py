"""The analysis sandbox's Python package environment.

Packages are installed into a dedicated, gitignored target and made importable
only by the analysis runner. Installation is approval-gated; the lock file is the
record of what is installed and which top-level modules are permitted.
"""

from __future__ import annotations

from .paths import env_root, installed_modules, installed_packages, read_lock, site_packages
from .provisioner import install, remove
from .tools import register_python_env_tools

__all__ = [
    "env_root",
    "install",
    "installed_modules",
    "installed_packages",
    "read_lock",
    "register_python_env_tools",
    "remove",
    "site_packages",
]
