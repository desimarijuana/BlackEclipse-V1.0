"""Deterministic MCP fixture servers for the Phase-5 test suite.

These are launched as real subprocesses by the tests through `MCPConnection`, so
they exercise the same stdio transport the runtime uses. They never touch the
network and require no API key.

Two fixtures:

  * `fastmcp_fixture.py` — a normal tool server built on the MCP SDK's
    `MCPServer` (formerly FastMCP). It advertises a read-only echo tool, a
    non-read write tool, and a deliberately malformed-schema tool.
  * `raw_fixture.py` — a hand-rolled JSON-RPC server so tests can deterministically
    simulate a crash, a malformed frame, an oversized output, and a slow call.
    Behaviour is selected by an argv flag.
"""
