"""Eclipse Browser Automation Runtime.

A first-class, provider-agnostic browser subsystem inspired by Hermes: a
tool-driven browser capability with multiple backends, isolated sessions,
accessibility-first observation, stable element references, programmatic
execution, a credential vault, a policy/security engine, provider routing, and
trace/telemetry — integrated into the existing Eclipse harness rather than a
parallel stack.

Layer map (mirrors the platform architecture):

    tools.py            the `browser_*` toolset registered on the ONE registry
    manager.py          the process-wide BrowserManager (sessions + pool)
    session.py          one BrowserSession: tabs, state machine, lifecycle
    router.py           BrowserProviderRouter (capability/policy-based selection)
    providers/          LocalChromium (Playwright), CDP, and honest remote stubs
    observation.py      accessibility-first snapshots with stable refs
    resolver.py         the locator/re-resolution engine
    verification.py     action → observe → verify
    vision.py           screenshot/a11y fusion fallback
    execution.py        `browser_exec` (sandboxed programmatic control)
    policy.py           permissions + domain policy + prompt-injection defense
    vault.py            credential references resolved internally (never to the model)
    profiles.py         persistent profiles
    store.py            durable metadata on the ONE agent-memory connection
    trace.py            structured BrowserTrace
    config.py           the `browser:` configuration section

Nothing here fabricates: a missing Playwright/Chromium is an honest
`UNAVAILABLE`, never a fake browser.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
