"""A hand-rolled JSON-RPC MCP server so tests can simulate hostile behaviour.

Behaviour is chosen by the first argv flag:
  normal       — advertise a read-only echo tool (+ a malformed-schema tool)
  big          — advertise `echo`; a call returns an oversized text payload
  slow         — advertise `echo`; a call sleeps before responding
  crash        — exit immediately after `initialize`
  malformed    — advertise a tool whose inputSchema is invalid
  duplicate    — advertise two distinct tool names that sanitize to one name
  secret_echo  — advertise `echo`; returns a configured env secret in the result
"""

import json
import os
import sys
import time

MODE = sys.argv[1] if len(sys.argv) > 1 else "normal"


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def tool(name, schema=None, description="tool"):
    return {
        "name": name,
        "description": description,
        "inputSchema": schema
        or {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "annotations": {"readOnlyHint": True},
    }


def tools_for_mode():
    if MODE == "malformed":
        return [tool("broken", {"type": "object", "properties": {"x": {"type": "weird"}}})]
    if MODE == "duplicate":
        return [tool("a-b"), tool("a.b"), tool("a_b")]
    if MODE == "normal":
        return [
            tool("echo", description="Echo text"),
            tool("write_thing", description="Non-read tool"),
        ]
    return [tool("echo")]


def handle(msg):
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        if MODE == "slowstart":
            time.sleep(5)
        send(
            {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-11-25"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "raw", "version": "1.0"},
                },
            }
        )
    elif method == "notifications/initialized":
        return
    elif method == "tools/list":
        if MODE == "slowcatalog":
            time.sleep(5)
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": tools_for_mode()}})
    elif method == "tools/call":
        name = (msg.get("params") or {}).get("name")
        args = (msg.get("params") or {}).get("arguments") or {}
        if MODE == "slow":
            time.sleep(5)
        if MODE == "big":
            text = "B" * 500_000
        elif MODE == "secret_echo":
            text = "secret=" + os.environ.get("FIXTURE_SECRET", "")
        elif name == "echo":
            text = "echo:" + str(args.get("text", ""))
        else:
            text = "unknown"
        send(
            {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": name != "echo",
                },
            }
        )
    else:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}})


def main():
    if MODE == "crash":
        # Close stdin immediately; the client will see EOF during initialize.
        return
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if MODE == "crash":
            return
        handle(msg)


main()
