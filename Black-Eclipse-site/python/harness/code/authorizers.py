"""The ONE composition of a run's effect authorizers.

Every non-read tool is authorized through the chain assembled here:

    git (dangerous / remote)  →  terminal / shell (allow|ask|deny)
        →  code write  →  code external action  →  MCP single-use approvals

Each layer is a thin wrapper that falls through to the next for a tool it does
not own, so adding a capability is one line and never touches the others. The
registry refuses every non-read tool when the chain ultimately returns False —
the safe default.

Extracted from `graph.py` so the graph module stays under its size ratchet and
the composition has exactly one home.
"""

from __future__ import annotations

from typing import Any, Optional

from . import policy


def build_effect_authorizer(
    approvals: Optional[Any],
    run_id: str,
    emitter: Any,
    workspace_id: Optional[str] = None,
) -> Optional[Any]:
    """Compose the run's effect authorizer.

    A `workspace_*` write is authorized by the run's autonomy profile; a `code_*`
    external action and a dangerous/remote Git operation require a single-use,
    workspace-bound operator approval; every other non-read tool falls to the MCP
    approvals authorizer. With no store wired every non-read tool is refused.
    """
    from .tools import make_code_authorizer  # noqa: PLC0415

    mcp_authorizer = None
    if approvals is not None:
        from ..mcp.approvals import make_effect_authorizer  # noqa: PLC0415

        mcp_authorizer = make_effect_authorizer(approvals, run_id, emitter)
    code_authorizer = make_code_authorizer(mcp_authorizer)

    # The execution + LOCAL application-runtime families (execute_*, build/test/
    # verify, service control, package/container/compose/runtime starts) run
    # bounded programs and manage local processes. Admitted at this seam exactly
    # like `command_run`: the HANDLER enforces the binding and the `code.execute`
    # grant, and the security gateway still classifies every call. Without this
    # branch they fell through to the MCP authorizer, which refuses any tool
    # without an MCP server id — leaving the tools advertised to code profiles
    # but dead (measured 2026-10-12: execute_python / execute_code /
    # build_project / start_service / package_install all False).
    code_authorizer = _admit_runtime_tools(code_authorizer)

    # Bulk acquisition (`acquire`): admitted HERE; the HANDLER enforces the
    # operator's master switch (`acquisition_enabled`, default OFF) and the
    # `data.collect` grant, and the collection itself runs through the read-only
    # bridge under its own budget (W3 slice of phase 16).
    code_authorizer = _admit_collect_tools(code_authorizer)

    # Benign LOCAL writes that carry no dedicated approval kind and whose handler
    # already enforces the binding/autonomy/grant (they persist to the user's own
    # store). Admitted here so they are not dead; without this branch they fell
    # through to the MCP authorizer and were refused while advertised.
    code_authorizer = _admit_local_writes(code_authorizer)

    # Generic terminal: an `allow` command runs, an `ask` command needs a
    # single-use workspace-bound approval, a `deny` is refused.
    from .terminal_tools import make_terminal_authorizer  # noqa: PLC0415

    code_authorizer = make_terminal_authorizer(code_authorizer)
    from .shell_tools import make_shell_authorizer  # noqa: PLC0415

    code_authorizer = make_shell_authorizer(code_authorizer)

    # The terminal subsystem's own tools, classified exactly like the shell tools.
    from ..terminal.tools import make_terminal_tool_authorizer  # noqa: PLC0415

    code_authorizer = make_terminal_tool_authorizer(code_authorizer)

    # The Git subsystem: a local mutation is admitted by the autonomy profile; a
    # dangerous/destructive op or any remote action needs a single-use approval.
    from ..git.approvals import make_git_authorizer  # noqa: PLC0415

    code_authorizer = make_git_authorizer(
        approvals, run_id, workspace_id or "", emitter, inner=code_authorizer,
    )

    # The browser subsystem: an effectful browser tool (run script / CDP / sandbox
    # program / upload / vault / interception) is admitted HERE; the handler's
    # browser POLICY engine enforces the per-permission verdict and routes an ASK
    # through the SAME single-use approval store. Every other non-read tool falls
    # through unchanged.
    from ..browser.authorizers import make_browser_authorizer  # noqa: PLC0415

    code_authorizer = make_browser_authorizer(code_authorizer)

    # The Computer Use Engine: an elevated computer tool (finance mutation, human
    # takeover) is admitted HERE and re-checked in the handler by the COMPUTER
    # POLICY engine and the FINANCE FIREWALL. `computer_use` itself is registered
    # read and gated per-call by the same policy engine.
    from ..computer.authorizers import make_computer_authorizer  # noqa: PLC0415

    code_authorizer = make_computer_authorizer(code_authorizer)

    # The Vision external action: `image_generate` is a paid, external provider
    # call. Admitted HERE and gated by a single-use operator approval (kind
    # `vision_external`); without this branch it fell through to the MCP authorizer
    # and was refused while advertised.
    from ..vision.authorizers import make_vision_authorizer  # noqa: PLC0415

    code_authorizer = make_vision_authorizer(
        approvals, run_id, workspace_id or "", emitter, inner=code_authorizer,
    )

    # The Portfolio Accounting Engine: a `portfolio_*` mutation (the
    # `portfolio.write` family and the consequential proposals) is admitted HERE
    # and requires a single-use, digest-bound operator approval
    # (kind `portfolio_write`). Without this branch the family fell through to the
    # MCP authorizer, which refuses any tool without an MCP server id — leaving the
    # tools advertised to ECLIPSE_AGENT but dead (measured 2026-10-14:
    # `portfolio_create` → TOOL_FORBIDDEN; identical to the runtime-family defect
    # fixed by `_admit_runtime_tools`).
    from ..portfolio.authorizers import make_portfolio_authorizer  # noqa: PLC0415

    code_authorizer = make_portfolio_authorizer(
        approvals, run_id, workspace_id or "", emitter, inner=code_authorizer,
    )

    # The General Ledger: a `ledger_*` MUTATION (effect `ledger.write`) is a write
    # to the book of record and requires a single-use, digest-bound operator
    # approval (kind `ledger_write`). Reads never reach an authorizer.
    from ..ledger.authorizers import make_ledger_authorizer  # noqa: PLC0415

    code_authorizer = make_ledger_authorizer(
        approvals, run_id, workspace_id or "", emitter, inner=code_authorizer,
    )

    # The Automation subsystem: the autonomous-schedule tools (bot_create/update/
    # enable/resume) are admitted HERE; the HANDLER claims or requests a single-use
    # operator approval (kind `bot_schedule`) before a schedule is created or
    # started, so an agent cannot quietly put itself on a cadence (R3-07).
    from ..automation.authorizers import make_bot_authorizer  # noqa: PLC0415

    code_authorizer = make_bot_authorizer(code_authorizer)

    # The scraper lane: `scraper_run` writes and runs a generated scraper. It is
    # admitted HERE and gated by a per-DOMAIN operator approval (kind
    # `scraper_domain`): the first collection from a site asks, and the consent
    # for that site is then remembered as a revocable standing grant.
    from ..scraper.authorizers import make_scraper_authorizer  # noqa: PLC0415

    code_authorizer = make_scraper_authorizer(
        approvals, run_id, workspace_id or "", emitter, inner=code_authorizer,
    )

    # The acquire loop: `skill_install`/`skill_uninstall` (GitHub skills) and
    # `mcp_install` (a preset MCP integration) each require a single-use,
    # digest-bound operator approval — the same card/decision store every other
    # capability uses. Composition order is irrelevant: each layer owns unique
    # tool names and falls through for everything else.
    from ..skills.install_tools import make_skill_authorizer  # noqa: PLC0415

    code_authorizer = make_skill_authorizer(code_authorizer)

    # The extension layer: agent-authored skills (`skill_create`/`skill_update`/
    # `skill_delete`) are DECLARATIVE (a validated manifest + bounded
    # instructions, never code) and each needs a single-use, digest-bound operator
    # approval. Composed here so the tools participate in the ONE chain.
    from ..skills.manage_tools import make_skill_manage_authorizer  # noqa: PLC0415

    code_authorizer = make_skill_manage_authorizer(code_authorizer)

    # The skill lifecycle: activating an evaluated version and switching automatic
    # skill learning are writes, each needing its own single-use operator approval.
    from ..skills.lifecycle_tools import make_skill_lifecycle_authorizer  # noqa: PLC0415

    code_authorizer = make_skill_lifecycle_authorizer(code_authorizer)

    # The analysis sandbox's Python package environment: install/remove are
    # separate, network-capable, single-use approval-gated mutations.
    from ..python_env.authorizers import make_python_env_authorizer  # noqa: PLC0415

    code_authorizer = make_python_env_authorizer(code_authorizer)
    from ..mcp.install_tools import make_mcp_install_authorizer  # noqa: PLC0415

    code_authorizer = make_mcp_install_authorizer(code_authorizer)

    # The trading Journal: `journal_add_trade` writes to the front door's own
    # store and needs a single-use, digest-bound operator approval; the read and
    # every other tool fall through.
    from ..journal_tools import make_journal_authorizer  # noqa: PLC0415

    code_authorizer = make_journal_authorizer(code_authorizer)

    # Graph Studio authoring: `create_workflow` writes a NEW workflow document
    # into the app catalog (the front door owns the planner, the IR validation
    # and the store). It is a reversible local write — it never runs the graph —
    # so admission happens here and no approval is invented for it.
    from ..graph_tools import make_graph_authorizer  # noqa: PLC0415

    code_authorizer = make_graph_authorizer(code_authorizer)

    if approvals is None or not workspace_id:
        code_authorizer = _wrap_with_money_guardrails(code_authorizer, run_id)
        return _wrap_with_security(code_authorizer, run_id, workspace_id)

    from .actions import make_code_action_authorizer  # noqa: PLC0415

    action_authorizer = make_code_action_authorizer(approvals, run_id, workspace_id, emitter)

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name.startswith("code_"):
            # A `code_*` EXTERNAL action (commit/push/open_pr/deploy) is owned by
            # the action authorizer; every other `code_*` tool (e.g. the CIUE
            # `code_rename_symbol`) is NOT — sending it only here refused it while
            # advertised. Try the action authorizer, then fall through to the full
            # code chain (which admits `is_code_write` names via its handler gate).
            if bool(await action_authorizer(tool, args, ctx)):
                return True
            return bool(await code_authorizer(tool, args, ctx))
        return bool(await code_authorizer(tool, args, ctx))

    from ..trade.authorizers import wrap_trade_authorizer  # noqa: PLC0415

    return _wrap_with_security(
        _wrap_with_money_guardrails(wrap_trade_authorizer(authorize), run_id),
        run_id, workspace_id,
    )


def _admit_runtime_tools(inner: Any) -> Any:
    """Admit the execution + LOCAL application-runtime families at this seam.

    The handlers enforce the workspace binding and the `code.execute` grant.
    K8s / Helm / Terraform / deploy mutations are deliberately NOT admitted here:
    they are approval-gated per action and stay on the approval path.
    """

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name in policy.EXECUTION_WRITE_TOOLS or name in policy.APP_RUNTIME_WRITE_TOOLS:
            return True
        return bool(await inner(tool, args, ctx))

    return authorize


def _admit_collect_tools(inner: Any) -> Any:
    """Admit the bulk-acquisition tool (`acquire`) at this seam.

    Admission is not authority: the HANDLER refuses unless the operator's switch
    (`acquisition_enabled`) is on AND the `data.collect` grant is held, and the
    collection runs through the read-only bridge under its own Python-enforced
    budget. Without this branch the tool would fall through to the MCP
    authorizer and be dead.
    """

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name in policy.DATA_COLLECT_TOOLS:
            return True
        return bool(await inner(tool, args, ctx))

    return authorize


# Benign LOCAL writes with no dedicated approval kind. The HANDLER enforces the
# binding, the autonomy profile and the grant; the tool persists to the user's own
# store. Admitted at this seam so an advertised tool is never dead. (The audit's
# visibility scan flags the class; adding a name here is the ONE change needed.)
_ADMIT_LOCAL_WRITES: frozenset[str] = frozenset({
    "learning_progress_update",
    # ML registry/local-artifact writes: the HANDLER enforces the workspace
    # binding and records every transition as an approval event + audit row.
    "ml_finetune_adapter",
    "ml_transition_model",
})


def _admit_local_writes(inner: Any) -> Any:
    """Admit the benign local-write family at this seam (handler-gated)."""

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name in _ADMIT_LOCAL_WRITES:
            return True
        return bool(await inner(tool, args, ctx))

    return authorize


_SHELL_TOOL_NAMES = frozenset({"terminal_run", "shell_run", "command_run"})


def _wrap_with_money_guardrails(inner: Any, run_id: str) -> Any:
    """Gate the shell/terminal surface through the money guardrails.

    `terminal_run` / `shell_run` / `command_run` can reach a broker or payment
    API. When the command names such a surface AND a money verb, the guardrail
    runs BEFORE the command's own approval. Every other tool falls through
    unchanged (computer/browser/MCP enforce at their own seams).
    """

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name not in _SHELL_TOOL_NAMES:
            return bool(await inner(tool, args, ctx))
        try:
            from ..finance_guardrails import get_service  # noqa: PLC0415
            from ..finance_guardrails.intent import intent_from_tool  # noqa: PLC0415

            service = get_service()
            if service is not None:
                intent = intent_from_tool(
                    name, args, run_id=str(getattr(ctx, "run_id", "") or run_id),
                )
                if intent is not None:
                    allowed, _verdict = await service.enforce(intent, ctx)
                    if not allowed:
                        return False
        except Exception:  # noqa: BLE001 - a failing guardrail must not authorize
            return False
        return bool(await inner(tool, args, ctx))

    return authorize


def _wrap_with_security(inner: Any, run_id: str, workspace_id: Optional[str]) -> Any:
    """Route the composed authorizer through the Security Gateway.

    The gateway is additive: it enforces the Security Floor and audits every
    filesystem/shell effect, then delegates to `inner` for the capability's own
    approval semantics. When no gateway is installed, `inner` is returned
    unchanged (the existing authority), never a permissive stub.
    """
    try:
        from ..security.bootstrap import get_gateway  # noqa: PLC0415

        gateway = get_gateway()
        if gateway is None:
            return inner
        from ..security.integration import make_security_authorizer  # noqa: PLC0415

        return make_security_authorizer(
            inner, run_id=run_id, workspace_id=workspace_id, gateway=gateway,
        )
    except Exception:  # noqa: BLE001 - the security layer must never weaken the chain
        return inner


__all__ = ["build_effect_authorizer"]
