"""A deterministic finance-workflow fixture MCP server.

Provides the tools an end-to-end finance workflow needs, offline:

  * `read_holdings`  (read)  — returns sample holdings as JSON text.
  * `export_report`  (write) — writes a report to a file under a temp dir and
                               returns the path. Write effect → needs approval.

Used by `tests/test_mcp_workflow.py`. No network, no real spreadsheet.
"""

import json
import os
import sys

from mcp import types
from mcp.server.mcpserver import MCPServer

server = MCPServer("finance-fixture", version="1.0.0")

HOLDINGS = [
    {"symbol": "AAPL", "market": "US", "quantity": 10, "cost": 150.0},
    {"symbol": "MSFT", "market": "US", "quantity": 5, "cost": 300.0},
    {"symbol": "NVDA", "market": "US", "quantity": 8, "cost": 90.0},
]


@server.tool(description="Read the sample holdings from the workbook.", annotations=types.ToolAnnotations(read_only_hint=True))
def read_holdings() -> str:
    return json.dumps({"rows": HOLDINGS})


@server.tool(description="Export a report to a spreadsheet file in the export directory.",
             annotations=types.ToolAnnotations(read_only_hint=False))
def export_report(name: str, content: str) -> str:
    out_dir = os.environ.get("FINANCE_EXPORT_DIR") or os.environ.get("BLACK_ECLIPSE_TMP") or "."
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return f"exported:{path}"


if __name__ == "__main__":
    server.run("stdio")
