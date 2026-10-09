"""UI Engineering CLI tests (`eclipse ui ...`)."""

from __future__ import annotations

import json
import os
import tempfile

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-ui-cli-"), "agent-memory.db"),
)

from harness.cli import main  # noqa: E402


def _out(capsys):
    return json.loads(capsys.readouterr().out)


def test_ui_components_and_capabilities(capsys):
    assert main(["--json", "ui", "components"]) == 0
    assert len(_out(capsys)["components"]) >= 1
    assert main(["--json", "ui", "capabilities"]) == 0
    assert _out(capsys)["componentCount"] >= 1


def test_ui_classify(capsys):
    assert main(["--json", "ui", "classify", "build a new backend API endpoint"]) == 0
    assert _out(capsys)["mode"] == "engineer"
    assert main(["--json", "ui", "classify", "move the chart below the timeline"]) == 0
    assert _out(capsys)["mode"] == "compose"


def test_ui_lifecycle_export_import(tmp_path, capsys):
    assert main(["--json", "ui", "create", "CLI Desk"]) == 0
    created = _out(capsys)["blueprint"]
    blueprint_id = created["id"]

    assert main(["--json", "ui", "show", blueprint_id]) == 0
    assert _out(capsys)["blueprint"]["id"] == blueprint_id

    out_path = tmp_path / "bp.json"
    assert main(["ui", "export", blueprint_id, "--path", str(out_path)]) == 0
    assert out_path.exists()
    capsys.readouterr()  # discard the export summary line

    assert main(["--json", "ui", "import", str(out_path)]) == 0
    imported = _out(capsys)["blueprint"]
    assert imported["id"] != blueprint_id

    assert main(["--json", "ui", "blueprints"]) == 0
    assert _out(capsys)["total"] >= 2
