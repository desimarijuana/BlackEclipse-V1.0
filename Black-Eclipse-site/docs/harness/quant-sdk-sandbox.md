# Python Strategy SDK — isolation, dependencies and the sandbox image

**Who this is for:** operators who run user-authored Python strategies
(`harness/quant/sdk_runtime.py`, tool `run_python_strategy` / `run_python_project`).

## Isolation modes

The worker (`harness/quant/sdk_worker.py`) can run two ways, chosen by
`resolve_sandbox()` in `quant/sdk_runtime.py`:

| Mode | When | What it enforces |
|---|---|---|
| **process** (default) | always available | separate process, `python -I`, a **scrubbed environment** (no PYTHONPATH, no credentials/provider keys), wall-clock **timeout**, **output-size cap**, POSIX `RLIMIT_CPU`/`RLIMIT_AS` where supported (Windows relies on timeout + output cap) |
| **docker** | `HARNESS_QUANT_SDK_DOCKER_IMAGE` is set **and** `docker` is on PATH | the process mode **plus** `--network none --read-only --memory 512m --cpus 1 --pids-limit 256 --tmpfs /tmp` |

The active mode is not inferred silently: without a configured image the runtime
uses **process** isolation. The capability is reported as `pythonStrategies:
partial` in `/quant/capabilities` unless a Docker image is configured.

## Building the sandbox image

From `Black-Eclipse-site/`:

```
docker build -f python/Dockerfile.quantsdk -t blackeclipse-quantsdk:latest python
```

Then enable it:

```
# PowerShell
setx HARNESS_QUANT_SDK_DOCKER_IMAGE blackeclipse-quantsdk:latest
# shell
export HARNESS_QUANT_SDK_DOCKER_IMAGE=blackeclipse-quantsdk:latest
```

The image is intentionally minimal (`python/requirements-quant-sdk.txt` = numpy,
pydantic, PyYAML) — the sdk invokes only the deterministic quant engine, never
the agent stack or provider clients.

## Dependency policy

`quant/sdk_deps.py` defines the **approved** numerical stack. `inspect_source`
(the `inspect_python_strategy` tool) classifies imports and flags
`UNAPPROVED_DEPENDENCY`; the runtime never installs packages on demand, so an
environment is pinned by the harness, not mutated per run.

## Verifying it end-to-end

`python/tests/test_quant_e2e_smoke.py` drives the whole chatbot flow through the
real tool registry: create → backtest → report → approve → deploy (paper) →
paper shadow run. `python/tests/test_quant_sdk_runtime.py` covers the process
sandbox (run, module/`on_data` error, timeout, empty source) and the sandbox
selection + Docker command construction.
