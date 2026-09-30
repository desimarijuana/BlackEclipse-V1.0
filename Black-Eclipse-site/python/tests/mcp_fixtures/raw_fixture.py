"""A hand-rolled JSON-RPC MCP server so tests can simulate hostile behaviour.

Behaviour is chosen by the first argv flag:
  normal       — advertise a read-only echo tool (+ a malformed-schema tool)
  big          — advertise `echo`; a call returns an oversized text payload
  slow         — advertise `echo`; a call sleeps before responding
  crash        — exit immediately after `initialize`
  malformed    — advertise a tool whose inputSchema is invalid
  duplicate    — advertise two distinct tool names that sanitize to one name
  secret_echo  — advertise `echo`; returns a configured env secret in the result
  crash_on_call— advertise `echo`; exit on the first tools/call (session drop)
  die_after_init — advertise `echo`; exit right after tools/list (drop at call)
  provider_error — advertise `echo`; a call returns a 401-style JSON error body
                   with `isError=False` (the provider reports the error in text)
  empty_result   — advertise `echo`; a call returns an empty text block
  notion_naming  — model the REAL Notion naming: `API-post-search` (a read with a
                   write-looking name), `API-move-page` / `API-patch-page` (writes
                   with no reliable write hint). All advertise readOnlyHint=True
                   so a test can prove the name alone must not activate.
  list_changed   — advertise `echo` + `transient`; on the first `tools/call` send
                   a `notifications/tools/list_changed`; every subsequent
                   tools/list drops `transient`. The trigger is a call (not the
                   initial listing) so a test controls timing and is race-free.
  list_changed_all — advertise tools+resources+prompts; on the first `tools/call`
                   send all three `list_changed` notifications; afterwards the
                   resource and prompt listings are reduced (one resource + one
                   prompt dropped), proving the utility snapshots refresh.
  fail_calls     — connect fine and list `echo`; every tools/call returns a
                   JSON-RPC error (a transport-level call failure) so the circuit
                   breaker can be exercised.
"""

import json
import os
import sys
import time

MODE = sys.argv[1] if len(sys.argv) > 1 else "normal"

# Tests that assert orphan reaping need the child's own pid; the fixture writes it
# to MCP_FIXTURE_PIDFILE when set (this is the direct child the SDK spawned).
_pidfile = os.environ.get("MCP_FIXTURE_PIDFILE")
if _pidfile:
    try:
        with open(_pidfile, "w", encoding="utf-8") as _fh:
            _fh.write(str(os.getpid()))
    except OSError:
        pass


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


_list_count = 0
_change_signalled = False


def _advertises_capabilities():
    """Which capabilities this mode advertises at initialize."""
    if MODE == "list_changed_all":
        return {"tools": {}, "resources": {}, "prompts": {}}
    return {"tools": {}}


def resources_for_mode():
    if MODE == "list_changed_all" and _change_signalled:
        return [{"uri": "note://kept", "name": "kept", "mimeType": "text/plain"}]
    if MODE == "list_changed_all":
        return [
            {"uri": "note://kept", "name": "kept", "mimeType": "text/plain"},
            {"uri": "note://dropped", "name": "dropped", "mimeType": "text/plain"},
        ]
    return []


def prompts_for_mode():
    if MODE == "list_changed_all" and _change_signalled:
        return [{"name": "kept_prompt", "description": "kept", "arguments": []}]
    if MODE == "list_changed_all":
        return [
            {"name": "kept_prompt", "description": "kept", "arguments": []},
            {"name": "dropped_prompt", "description": "dropped", "arguments": []},
        ]
    return []


def tools_for_mode():
    global _list_count
    if MODE == "malformed":
        return [tool("broken", {"type": "object", "properties": {"x": {"type": "weird"}}})]
    if MODE == "duplicate":
        return [tool("a-b"), tool("a.b"), tool("a_b")]
    if MODE == "normal":
        return [
            tool("echo", description="Echo text"),
            tool("write_thing", description="Non-read tool"),
        ]
    if MODE == "notion_naming":
        # Real Notion names, all lying `readOnlyHint=True` (the server's own hint
        # is untrusted). `API-post-search` is a READ; `API-move-page` is a write.
        return [
            tool("API-post-search", description="Search (a read with a write-looking name)"),
            tool("API-move-page", description="Move a page (a write with no write hint)"),
            tool("API-patch-page", description="Patch a page (a write)"),
        ]
    if MODE == "list_changed":
        # The listing includes `transient` until a call has signalled the change.
        if _change_signalled:
            return [tool("echo", description="Echo text")]
        return [tool("echo", description="Echo text"), tool("transient", description="Goes away")]
    return [tool("echo")]


def handle(msg):
    global _change_signalled, _list_count
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
                    "capabilities": _advertises_capabilities(),
                    "serverInfo": {"name": "raw", "version": "1.0"},
                },
            }
        )
    elif method == "notifications/initialized":
        return
    elif method == "tools/list":
        _list_count += 1
        if MODE == "slowcatalog":
            time.sleep(5)
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": tools_for_mode()}})
        if MODE == "die_after_init":
            sys.exit(0)
    elif method == "resources/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"resources": resources_for_mode()}})
    elif method == "prompts/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"prompts": prompts_for_mode()}})
    elif method == "tools/call":
        name = (msg.get("params") or {}).get("name")
        args = (msg.get("params") or {}).get("arguments") or {}
        if MODE == "crash_on_call":
            # Drop the session without answering: the client sees EOF/closed.
            sys.exit(0)
        if MODE == "list_changed" and not _change_signalled:
            # Announce the catalog change once, on the first call, then answer it.
            _change_signalled = True
            send({"jsonrpc": "2.0", "method": "notifications/tools/list_changed", "params": {}})
        if MODE == "list_changed_all" and not _change_signalled:
            # Announce all three listing changes once; afterwards the resource and
            # prompt listings are reduced.
            _change_signalled = True
            for method_name in (
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
                "notifications/prompts/list_changed",
            ):
                send({"jsonrpc": "2.0", "method": method_name, "params": {}})
        if MODE == "fail_calls":
            # A server that connected and lists tools, but fails every call at the
            # transport/JSON-RPC layer (not a provider-side error body).
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32000, "message": "call failed"}})
            return
        if MODE == "slow":
            time.sleep(5)
        if MODE == "big":
            text = "B" * 500_000
        elif MODE == "secret_echo":
            text = "secret=" + os.environ.get("FIXTURE_SECRET", "")
        elif MODE == "provider_error":
            # The provider reports the failure INSIDE a normal text block while
            # `isError` stays false, exactly like Notion's 401 body.
            send(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "content": [{
                            "type": "text",
                            "text": '{"status":401,"object":"error","code":"unauthorized",'
                                    '"message":"API token is invalid."}',
                        }],
                        "isError": False,
                    },
                }
            )
            return
        elif MODE == "empty_result":
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [], "isError": False}})
            return
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
