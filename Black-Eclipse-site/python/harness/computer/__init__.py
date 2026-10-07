"""Eclipse Computer Use Engine.

A production-grade, platform-aware, finance-aware desktop-control runtime. It is
a first-class capability of the Eclipse harness — registered on the SAME
`ToolRegistry`, gated by the SAME permission/approval architecture, persisted on
the SAME `agent-memory.db`, and observable on the SAME event bus. It is NOT a
parallel stack.

The fundamental loop is observe → understand → plan → ground → authorize → act →
observe → verify → (recover | done). Coordinate clicking is the LAST resort; the
grounding hierarchy is accessibility → semantic → structured UI → OCR → vision →
relative coordinate → raw coordinate.

Computer Use is deliberately SEPARATE from the browser subsystem
(`python/harness/browser/`). The browser owns DOM/HTML/page operations; Computer
Use owns native desktop applications, OS chrome, file pickers, dialogs, Excel,
VS Code, terminals, PDF apps and financial terminals — anything outside a page's
DOM. The two coexist and are chosen by task shape.

Layer map:

    core.py             the platform-independent orchestrator (the ONE loop)
    session.py          one ComputerSession (state, snapshots, target, history)
    manager.py          the process-wide ComputerManager (sessions + lease)
    drivers/            ComputerDriver implementations (windows / null)
    accessibility/      AX providers (UIA on Windows; honest stubs elsewhere)
    vision/             screenshot + VLM abstraction (local/cloud/hybrid)
    ocr/                first-class OCR (text + boxes + confidence)
    grounding/          TargetGrounder (the hierarchy)
    actions/            mouse / keyboard engines + semantic set_value
    windows/            window management
    applications/       application management + ApplicationAdapter framework
    sessions/           session persistence + isolated desktop lifecycle
    screenshots/        screen capture + region intelligence + change detection
    verification/       ActionVerifier + screen diff
    recovery/           RecoveryEngine (the ladder) + verdicts
    policy/             permission engine + app/action allow-deny
    security/           sensitive-region detection + redaction
    finance/            financial extraction, firewall, risk modes, provenance
    takeover/           control lease / human takeover
    recording/          trajectories (record/export/inspect)
    replay/             deterministic replay
    telemetry/          metrics
    diagnostics/        doctor / capability report
    adapters/           per-application adapters (excel, vscode, terminal, …)
    tools.py            the `computer_*` agent toolset
    schemas.py          model-facing JSON schemas + tool metadata

Nothing here fabricates: a missing driver/OCR/AX/vision backend is an honest
`UNAVAILABLE`, never a fake desktop.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
