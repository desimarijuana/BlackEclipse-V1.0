"""Loopback callback helpers for front-door-owned SDK routes.

The theme, app-shell and dashboard-template surfaces live in the Next.js front
door (JDDS `SystemConfig` and the TypeScript template registry). Python tools
reach them over the same authenticated loopback callback the Journal write uses.
"""

from __future__ import annotations

import os


def callback_base() -> str:
    return (
        os.environ.get("HARNESS_CALLBACK_URL")
        or f"http://127.0.0.1:{os.environ.get('PORT', '3000')}"
    ).rstrip("/")


def callback_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("CRON_SECRET")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


__all__ = ["callback_base", "callback_headers"]
