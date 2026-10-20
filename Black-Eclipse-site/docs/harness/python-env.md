---
title: Python Package Environment (analysis sandbox)
status: Current
last-verified: 2026-10-19
---

# Python Package Environment

**Who this is for:** anyone changing how Eclipse installs packages used by
`analysis_run`, generated recipes, or reports.

## What it is

Eclipse keeps the analysis sandbox's third-party packages in a dedicated,
gitignored target:

```
.black-eclipse/
  python-env/
    site-packages/       installed packages
    lock.json            package names, versions, top-level modules, timestamp
  pip-cache/             the download/wheel cache
```

The vendored analysis interpreter is never modified. `run_analysis` adds the
managed target to the runner's `sys.path` and treats the lock's top-level modules
as permitted imports alongside the built-in `IMPORT_ALLOWLIST`.

## Tools

| Tool | Behavior |
|---|---|
| `python_env_install` | Install plain package specs (optional version) into the managed target. Single-use operator approval. |
| `python_env_remove` | Remove installed packages and update the lock. Single-use operator approval. |
| `python_env_list` | Read installed packages, modules and the lock digest. Read-only. |
| `python_env_status` | Report the target, cache, lock digest and interpreter. Read-only. |

## Approval and policy

- Install/remove are `write` tools and are admitted only through
  `python_env/authorizers.py`. The authorizer consumes a single-use,
  digest-bound approval (`python_env_install` / `python_env_remove`); with no
  approval it creates the pending request and, in approval-card mode, pauses.
  The agent cannot self-grant.
- Only plain package names with optional version constraints are accepted.
  URLs, local paths and VCS sources are refused (`PACKAGE_SPEC_INVALID`).
- The pip process is an absolute interpreter, an argv list with no shell, the
  scrubbed environment (no proxy/secrets), a private cache, a bounded timeout
  and bounded output. A failed install leaves the lock unchanged.
- The lock records exactly what was installed and is the import allowlist source.

## Network boundary

Package installation is a separate, approval-gated network lane; generated code
still runs with the sandbox's restricted imports and builtins. An installed
package is **trusted code**: on the local tier an approved package that opens a
socket is not OS-isolated, because the local backend does not provide a network
namespace. A deployment that requires hard network isolation must use the
container tier (`code/backends.py`) for analysis runs. This limitation is
documented rather than hidden.

## Tests

`python/tests/test_python_env.py` covers spec validation, install/lock writes,
removal, approval request/consume, tool registration, and an analysis run that
imports a package from the managed target.
