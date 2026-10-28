"""Live smoke runner for the Channel Gateway.

Talks to a running Eclipse Python runtime (default http://127.0.0.1:8765).
Loopback is authorized without a token; for a remote runtime set CRON_SECRET.

Examples:
  python scripts/channels_smoke.py --health
  python scripts/channels_smoke.py --list
  python scripts/channels_smoke.py --link lark --scope assistant
  python scripts/channels_smoke.py --send slack C123 "hello from Eclipse"
  python scripts/channels_smoke.py --bindings
  python scripts/channels_smoke.py --inbound webhook u1 "hi" --message-id m1
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx


def _base_url() -> str:
    return (os.environ.get("HARNESS_PY_URL") or "http://127.0.0.1:8765").rstrip("/")


def _headers() -> dict[str, str]:
    token = os.environ.get("CRON_SECRET")
    return {"X-Harness-Operator": token} if token else {}


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    with httpx.Client(base_url=_base_url(), timeout=30.0, headers=_headers()) as client:
        res = client.request(method, path, json=body)
    try:
        payload = res.json()
    except ValueError:
        payload = res.text
    if res.status_code >= 300:
        print(f"HTTP {res.status_code}: {json.dumps(payload, indent=2, default=str)}", file=sys.stderr)
        raise SystemExit(1)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Eclipse channel smoke runner")
    parser.add_argument("--health", action="store_true", help="gateway health + channel status")
    parser.add_argument("--list", action="store_true", help="list channels (redacted config)")
    parser.add_argument("--bindings", action="store_true", help="list linked bindings")
    parser.add_argument("--link", metavar="KIND", help="mint a link code for a channel")
    parser.add_argument("--scope", default="assistant", choices=("viewer", "assistant", "operator"))
    parser.add_argument("--send", nargs=3, metavar=("KIND", "CHAT", "TEXT"), help="send one outbound message")
    parser.add_argument("--file", action="append", default=[], help="attach a local file to --send (repeatable)")
    parser.add_argument("--inbound", nargs=3, metavar=("KIND", "EXTERNAL_ID", "TEXT"), help="inject a normalized inbound")
    parser.add_argument("--message-id", default="", help="platform message id for --inbound")
    args = parser.parse_args()

    if not any([args.health, args.list, args.bindings, args.link, args.send, args.inbound]):
        args.health = True

    if args.health:
        print(json.dumps(_request("GET", "/channels/health"), indent=2))
    if args.list:
        print(json.dumps(_request("GET", "/channels"), indent=2))
    if args.bindings:
        print(json.dumps(_request("GET", "/channels/bindings"), indent=2))
    if args.link:
        print(json.dumps(
            _request("POST", "/channels/link-code", {"kind": args.link, "scope": args.scope}),
            indent=2,
        ))
    if args.send:
        kind, chat, text = args.send
        attachments = []
        for path in args.file:
            raw = Path(path).read_bytes()
            attachments.append({
                "name": Path(path).name,
                "mimeType": "",
                "contentBase64": base64.b64encode(raw).decode("ascii"),
            })
        print(json.dumps(
            _request("POST", "/channels/send", {
                "kind": kind,
                "chat": chat,
                "text": text,
                "attachments": attachments,
            }),
            indent=2,
        ))
    if args.inbound:
        kind, external_id, text = args.inbound
        print(json.dumps(
            _request("POST", "/channels/inbound", {
                "kind": kind,
                "externalId": external_id,
                "externalChat": external_id,
                "text": text,
                "platformMessageId": args.message_id,
            }),
            indent=2,
        ))


if __name__ == "__main__":
    main()
