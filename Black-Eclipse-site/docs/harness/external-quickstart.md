---
title: External Quickstart (installed harness)
status: Current
last-verified: 2026-11-12
---

# External quickstart

This is the path for a user who is **not** in this repository.

## Install

```bash
python -m pip install black-eclipse-harness
python -c "import harness; print(harness.__version__)"
```

The package carries the runtime only: agents, tools, providers, events,
persistence, the evaluation/conformance suites and the ACP adapter. It carries
no app data, no vault, no database and no credentials. Install provider extras
you need:

```bash
python -m pip install "black-eclipse-harness[providers]"
```

## Run an agent

```python
import asyncio
from harness.public import AgenticService, RunInput, RunRequest, ModelSettings

async def main():
    service = AgenticService()
    result = await service.run(RunRequest(
        runId="demo-1",
        input=RunInput(query="What is 2 + 2?"),
        modelSettings=ModelSettings(provider="ollama", model="llama3.1",
                                    base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    ))
    print(result.status, result.output)

asyncio.run(main())
```

## Prove the install

```bash
python -m harness.evaluation.conformance --quick   # fault matrix + golden + contracts
python -m harness.acp --self-test                  # ACP handshake + one prompt
python -c "from harness.public import tool_manifest; print(tool_manifest()['digest'])"
```

The conformance suite is offline: no provider, network or data file is needed.
A missing optional benchmark is reported `unavailable`, never as a pass.

## Plugin

A minimal plugin is a directory with `plugin.json` (or `plugin.yaml`) and a
Python entrypoint. Install with an operator review and, if the operator requires
it, a signature:

```python
await manager.install("path/to/plugin", operator=True)
```

See `plugin-platform.md` for the manifest contract, the SDK version and the
signature/review gate.

## ACP

```bash
python -m harness.acp            # JSON-RPC 2.0 over stdio
python -m harness.acp --self-test
```

Supported: `initialize`, `session/new`, `session/prompt`, `session/cancel`,
`shutdown`. Unsupported methods are a typed `-32601` error, never a fake result.
