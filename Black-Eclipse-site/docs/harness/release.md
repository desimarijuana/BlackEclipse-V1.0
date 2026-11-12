---
title: Release runbook
status: Current
last-verified: 2026-11-12
---

# Release runbook

## Gate order

```bash
npm run release:check        # package/pyproject/harness versions agree
npm run gate:conformance     # C8 invariants
npm run gate:external        # offline fixture adapters
npm run gate:slo             # C7 budgets + baseline
npm run scorecard:from-runs  # regenerate the scorecard from a real run
node scripts/check-all.js    # the full local release gate
```

All must pass, with `npx tsc --noEmit` clean and the full Python suite green.

## Build

```bash
npm run package:python       # dist/black_eclipse_harness-<version>-py3-none-any.whl
```

The wheel excludes app data, `.env`, `*.db`, the vault and credentials. It
includes `harness/py.typed`, the datasets/fixtures and the conformance/ACP
entrypoints.

## Install smoke (no network)

```bash
python -m pip install --no-deps --target /tmp/be-pkg dist/*.whl
python -c "import sys; sys.path.insert(0,'/tmp/be-pkg'); import harness; print(harness.__version__)"
python -c "import sys, runpy; sys.path.insert(0,'/tmp/be-pkg'); sys.argv=['x','--quick']; runpy.run_module('harness.evaluation.conformance', run_name='__main__')"
python -c "import sys; sys.path.insert(0,'/tmp/be-pkg'); from harness.acp.server import _self_test; import asyncio; raise SystemExit(asyncio.run(_self_test()))"
```

## Tag and publish (operator)

1. Update `package.json`, `pyproject.toml` and `harness.__version__` together.
2. Append the CHANGELOG entry; regenerate `scorecard.json`/`.md`.
3. Commit, tag `v<version>`, push the tag.
4. Build the wheel/sdist; upload with the operator's PyPI credentials (never in
   the repo); attach checksums to the GitHub release.
5. Keep `dist/` out of git.

Publishing and the tag are operator steps: the repository never stores registry
credentials.
