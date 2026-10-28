"""Skill lifecycle tools — read history/reviews and switch learning on or off.

The Skills UI already exposes version history, reviews and activation, but the
agent had no bound surface for any of them (a self-improvement test asked for
version history, review data and a learning switch and got three refusals). This
module adds the missing surface WITHOUT a second lifecycle:

  * `skill_version_history` — read every retained version (status, evaluation,
    patch/canary metadata) through `versioning.version_history`.
  * `skill_reviews` — read the review + evaluation trail for a skill (optionally
    one version).
  * `skill_learning_get` — read the persisted skill-learning mode.
  * `skill_version_evaluate` — run the deterministic evaluation and persist the
    structured record through `versioning.evaluate_version`.
  * `skill_version_activate` — enable a version through
    `versioning.activate_version`; a passing evaluation is still required.
  * `skill_learning_set` — set `skill_learning_mode` through the normal
    `PolicyStore` validation (never a raw write).

The three writes are `write`-permission, effectful tools, removed at `plan_only`
(they join `ACQUISITION_WRITE_TOOLS`) and each gated by a single-use,
digest-bound operator approval via `make_skill_lifecycle_authorizer`.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from ..tools import ToolDefinition, ToolRegistry
from .permissions import Actor

LIFECYCLE_TOOLS: tuple[str, ...] = (
    "skill_version_evaluate",
    "skill_version_activate",
    "skill_learning_set",
)

LEARNING_MODES: tuple[str, ...] = ("off", "ask_before_saving", "automatic_selective")


def _registry_of(ctx: Any) -> Any:
    return getattr(ctx, "skill_registry", None)


def _digest(kind: str, subject: str, body: str = "") -> str:
    payload = f"{kind}\x00{subject}\x00{body}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _actor(ctx: Any) -> Actor:
    return Actor(id=str(getattr(ctx, "user_id", None) or "local"), operator=True)


# ── read handlers ─────────────────────────────────────────────────────────────


async def skill_version_history_handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    registry = _registry_of(ctx)
    if registry is None:
        return "Skills are not available in this run.", {"found": False, "versions": []}
    skill_id = str(args.get("skill_id") or args.get("name") or "").strip()
    if not skill_id:
        return "A skill id is required.", {"found": False, "versions": []}
    if registry.manifest(skill_id) is None:
        # Store-only learned skills are not in the in-memory catalog until a
        # reader materialises them. Try that before declaring the skill missing.
        try:
            registry.load_stored(skill_id)
        except Exception:  # noqa: BLE001 - an unreadable row is not a missing name
            pass
    if registry.manifest(skill_id) is None:
        return f"No skill named {skill_id!r}. Use skill_list to see available skills.", {
            "found": False, "versions": [],
        }
    try:
        from .versioning import version_history  # noqa: PLC0415

        versions = version_history(registry, skill_id)
    except Exception as exc:  # noqa: BLE001 - a store read failure is reported, never hidden
        return f"Could not read version history: {exc}", {"found": False, "error": "READ_FAILED"}
    record = registry.store.get_skill(skill_id) or {}
    latest = record.get("latestVersion")
    lines = [
        f"{skill_id}: {len(versions)} retained version(s); latest = {latest or '(none)'} "
        "(latest is the version a reload would run; its status says whether it is enabled)."
    ]
    for item in versions:
        bits = [f"v{item.get('version')}", str(item.get("status"))]
        if item.get("evaluationStatus"):
            bits.append(f"eval={item['evaluationStatus']}")
        # Emit an explicit value for every lineage field. `none` means the stored
        # column is empty (a root version, or never canaried); it is NOT the same
        # as "the endpoint did not report it", so the model never has to infer.
        base = f"v{item['baseVersion']}" if item.get("baseVersion") else "none"
        bits.append(f"base={base}")
        bits.append(f"canary={item.get('canaryState') or 'none'}")
        bits.append(f"activated={item.get('activatedAt') or 'none'}")
        if item.get("nonActivationCause"):
            bits.append(f"notActivated={item['nonActivationCause']}")
        if item.get("rolledBackAt"):
            bits.append(f"rolledBack={item['rolledBackAt']}")
        if item.get("patchSummary"):
            bits.append(f"patch={item['patchSummary']}")
        suffix = " (latest)" if item.get("version") == latest else ""
        lines.append(f"  - {', '.join(bits)}{suffix}")
    return "\n".join(lines), {
        "found": True, "skillId": skill_id, "latestVersion": latest,
        "activeVersion": latest, "versions": versions,
    }


async def skill_reviews_handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    registry = _registry_of(ctx)
    if registry is None:
        return "Skills are not available in this run.", {"found": False, "reviews": [], "evaluations": []}
    skill_id = str(args.get("skill_id") or args.get("name") or "").strip()
    if not skill_id:
        return "A skill id is required.", {"found": False, "reviews": [], "evaluations": []}
    if registry.manifest(skill_id) is None:
        return f"No skill named {skill_id!r}. Use skill_list to see available skills.", {
            "found": False, "reviews": [], "evaluations": [],
        }
    try:
        limit = max(1, min(int(args.get("limit") or 20), 100))
    except (TypeError, ValueError):
        limit = 20
    version = str(args.get("version") or "").strip() or None
    try:
        reviews = registry.store.list_reviews(skill_id, limit)
        evaluations = registry.evaluation_history(skill_id)
    except Exception as exc:  # noqa: BLE001
        return f"Could not read skill reviews: {exc}", {"found": False, "error": "READ_FAILED"}
    if version:
        reviews = [r for r in reviews if str(r.get("version")) == version]
        evaluations = [e for e in evaluations if str(e.get("version")) == version]
    reviews = reviews[:limit]
    evaluations = evaluations[:limit]
    lines = [
        f"{skill_id}{f' v{version}' if version else ''}: "
        f"{len(reviews)} review(s), {len(evaluations)} evaluation(s)."
    ]
    for review in reviews:
        lines.append(
            f"  review {review.get('id')} v{review.get('version')} "
            f"{review.get('decision')} by {review.get('actor')} at {review.get('createdAt')} "
            f"— {review.get('notes') or ''}".rstrip()
        )
    for evaluation in evaluations:
        dims = evaluation.get("dimensions") or []
        dim_text = ", ".join(
            f"{d.get('name')}={d.get('status')}" for d in dims if d.get("name")
        )
        line = (
            f"  evaluation v{evaluation.get('version')} "
            f"{evaluation.get('status') or evaluation.get('decision') or ''} "
            f"at {evaluation.get('createdAt')}"
        )
        if evaluation.get("summary"):
            line += f" — {evaluation['summary']}"
        lines.append(line)
        if dim_text:
            lines.append(f"    dimensions: {dim_text}")
        for dim in dims:
            # The regression detail names the comparison baseline, so it must be
            # shown even when it PASSED — otherwise "passed" is unfalsifiable.
            if (
                dim.get("name") in ("regression", "discrimination")
                or dim.get("status") in ("failed", "needs_review")
            ) and dim.get("detail"):
                lines.append(f"    {dim.get('name')}: {dim.get('detail')}")
    if evaluations and any(
        d.get("name") == "regression" and d.get("status") == "needs_review"
        for d in (evaluations[0].get("dimensions") or [])
    ):
        lines.append(
            "  Note: the LATEST evaluation reports regression=needs_review because no "
            "prior evaluation exists; evaluate the base version first, then re-evaluate "
            "the candidate."
        )
    if not reviews and not evaluations:
        lines.append("  (no review or evaluation rows recorded)")
    return "\n".join(lines), {
        "found": True,
        "skillId": skill_id,
        "version": version,
        "reviews": reviews,
        "evaluations": evaluations,
    }


async def skill_discrimination_check_handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Read-only discrimination check with caller-supplied metrics.

    Proves the identical/better/worse rules without persisting an evaluation.
    """
    registry = _registry_of(ctx)
    if registry is None:
        return "Skills are not available in this run.", {"available": False}
    skill_id = str(args.get("skill_id") or args.get("name") or "").strip()
    version = str(args.get("version") or "").strip()
    if not skill_id or not version:
        return "skill_id and version are required.", {"available": False}
    if registry.manifest(skill_id) is None:
        return f"No skill named {skill_id!r}.", {"available": False}
    from .evaluation import _discrimination_dimension  # noqa: PLC0415

    try:
        prior = [
            e for e in registry.store.list_evaluations(skill_id, limit=50)
            if str(e.get("status")) != "superseded"
        ]
    except Exception:  # noqa: BLE001
        prior = []
    dimension = _discrimination_dimension(
        registry.store, skill_id, version,
        base_version=args.get("baseVersion"),
        metrics=args.get("metrics"),
        base_metrics=args.get("baseMetrics"),
        prior_evaluations=prior,
    )
    text = (
        f"discrimination={dimension.get('status')} "
        f"(mandatory={bool(dimension.get('mandatory'))}): {dimension.get('detail')}"
    )
    return text, dimension


async def skill_learning_get_handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = getattr(ctx, "memory_service", None)
    if service is None or getattr(service, "policy", None) is None:
        return "Skill learning policy is not available in this run.", {
            "found": False, "error": "POLICY_UNAVAILABLE",
        }
    try:
        settings = service.policy.get_all()
    except Exception as exc:  # noqa: BLE001
        return f"Could not read the learning policy: {exc}", {"found": False, "error": "READ_FAILED"}
    mode = settings.get("skill_learning_mode")
    detection = settings.get("auto_candidate_detection")
    return (
        f"Skill learning mode is {mode} (automatic candidate detection = {detection}).",
        {
            "found": True,
            "mode": mode,
            "autoCandidateDetection": detection,
        },
    )


# ── write handlers ────────────────────────────────────────────────────────────


async def skill_version_evaluate_handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    registry = _registry_of(ctx)
    if registry is None:
        return "Skills are not available in this run.", {"evaluated": False, "error": "SKILLS_UNAVAILABLE"}
    skill_id = str(args.get("skill_id") or args.get("name") or "").strip()
    version = str(args.get("version") or "").strip()
    if not skill_id or not version:
        return "A skill id and version are required.", {"evaluated": False, "error": "MISSING_INPUT"}
    from .versioning import evaluate_version  # noqa: PLC0415

    result = evaluate_version(registry, skill_id, version, actor=_actor(ctx))
    if not result.get("ok"):
        return f"Evaluation did not run: {result.get('error')}", {"evaluated": False, **result}
    status = result.get("status")
    record = result.get("record") or {}
    passed = record.get("passed", 0)
    failed = record.get("failed", 0)
    dims = result.get("dimensions") or []
    dim_text = ", ".join(
        f"{d.get('name')}={d.get('status')}" for d in dims if d.get("name")
    )
    lines = [
        f"Evaluated {skill_id} v{version}: {status} "
        f"({passed} dimension(s) passed, {failed} failed)."
    ]
    if result.get("summary"):
        lines.append(f"Summary: {result['summary']}")
    if dim_text:
        lines.append(f"Dimensions: {dim_text}")
    for dim in dims:
        if dim.get("status") in ("failed", "needs_review") and dim.get("detail"):
            lines.append(f"  {dim.get('name')}: {dim.get('detail')}")
    regression = next((d for d in dims if d.get("name") == "regression"), None)
    if regression and regression.get("detail"):
        lines.append(f"Regression baseline: {regression['detail']}")
    if status == "passed":
        lines.append("Activation now has a basis.")
    else:
        lines.append("A PASSING evaluation is required before activation.")
        if any(
            d.get("name") == "regression" and d.get("status") == "needs_review"
            for d in dims
        ):
            lines.append(
                "Regression has no baseline: evaluate the base version first, then "
                "re-evaluate this version."
            )
    return "\n".join(lines), {"evaluated": True, **result}


async def skill_version_activate_handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    registry = _registry_of(ctx)
    if registry is None:
        return "Skills are not available in this run.", {"activated": False, "error": "SKILLS_UNAVAILABLE"}
    skill_id = str(args.get("skill_id") or args.get("name") or "").strip()
    version = str(args.get("version") or "").strip()
    if not skill_id or not version:
        return "A skill id and version are required.", {"activated": False, "error": "MISSING_INPUT"}
    from .versioning import activate_version  # noqa: PLC0415

    result = activate_version(
        registry, skill_id, version,
        actor=_actor(ctx),
        canary=bool(args.get("canary")),
        reason=str(args.get("reason") or "operator-approved activation from chat"),
    )
    if not result.get("ok"):
        return f"Version not activated: {result.get('error')}", {"activated": False, **result}
    state = result.get("status")
    return (
        f"Activated {skill_id} v{version} ({state})."
        if not result.get("canary")
        else f"Started canary for {skill_id} v{version}.",
        {"activated": True, **result},
    )


async def skill_learning_set_handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = getattr(ctx, "memory_service", None)
    if service is None or getattr(service, "policy", None) is None:
        return "Skill learning policy is not available in this run.", {
            "updated": False, "error": "POLICY_UNAVAILABLE",
        }
    mode = str(args.get("mode") or "").strip()
    if mode not in LEARNING_MODES:
        return (
            f"Unknown mode {mode!r}; choose one of {', '.join(LEARNING_MODES)}.",
            {"updated": False, "error": "INVALID_MODE", "allowed": list(LEARNING_MODES)},
        )
    try:
        # PolicyStore.validate enforces the mode vocabulary and the hard floors;
        # there is no raw write path here.
        result = service.policy.set(
            "skill_learning_mode", mode,
            updated_by=str(getattr(ctx, "user_id", None) or "agent"),
        )
    except Exception as exc:  # noqa: BLE001
        return f"Skill learning was not changed: {exc}", {"updated": False, "error": "POLICY_REJECTED"}
    resolved = service.policy.get_all()
    return (
        f"Skill learning mode is now {result.get('value')} "
        f"(automatic candidate detection = {resolved.get('auto_candidate_detection')}).",
        {
            "updated": True,
            "mode": result.get("value"),
            "autoCandidateDetection": resolved.get("auto_candidate_detection"),
        },
    )


# ── registration ──────────────────────────────────────────────────────────────


def register_skill_lifecycle_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="skill_version_history",
            description=(
                "Read a skill's retained versions (status, evaluation, patch/canary "
                "metadata) and which version is active. Read-only; use it before asking "
                "about a patch or a regression."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string", "description": "The skill id."},
                },
                "required": ["skill_id"],
                "additionalProperties": False,
            },
            handler=skill_version_history_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_reviews",
            description=(
                "Read a skill's review and evaluation trail (optionally for one "
                "version). Invoking a skill does NOT create a review; reviews come from "
                "explicit evaluation/review decisions. Read-only."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string", "description": "The skill id."},
                    "version": {"type": "string", "description": "Optional version filter."},
                    "limit": {"type": "integer", "description": "Max rows (1-100, default 20)."},
                },
                "required": ["skill_id"],
                "additionalProperties": False,
            },
            handler=skill_reviews_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_discrimination_check",
            description=(
                "Read-only discrimination check: compare a version against a named "
                "base using caller-supplied outcome metrics. Returns failed when the "
                "metrics are identical or worse, passed when one improves, and an "
                "explicit gap when metrics are absent. Persists nothing."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    "version": {"type": "string"},
                    "baseVersion": {"type": "string"},
                    "metrics": {"type": "object"},
                    "baseMetrics": {"type": "object"},
                },
                "required": ["skill_id", "version"],
                "additionalProperties": False,
            },
            handler=skill_discrimination_check_handler,
            permission="read",
            risk="none",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_learning_get",
            description=(
                "Read the PERSISTED automatic skill-learning mode and the derived "
                "candidate-detection flag. Read-only; use it to verify a "
                "skill_learning_set write at rest."
            ),
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=skill_learning_get_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_version_evaluate",
            description=(
                "Run the deterministic evaluation for one skill version and persist "
                "the structured record (dimensions, pass/fail, regression vs. base). "
                "Activation still requires a PASSING result; the evaluation itself "
                "never enables or promotes anything. Requires an operator approval."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string", "description": "The skill id."},
                    "version": {"type": "string", "description": "The version to evaluate."},
                },
                "required": ["skill_id", "version"],
                "additionalProperties": False,
            },
            handler=skill_version_evaluate_handler,
            permission="write",
            risk="low",
            effect="write",
            timeout_ms=60_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_version_activate",
            description=(
                "Enable one evaluated skill version (or start a canary). A passing "
                "evaluation is required; the prior active version is superseded, never "
                "deleted. Requires an operator approval."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string", "description": "The skill id."},
                    "version": {"type": "string", "description": "The version to enable."},
                    "canary": {"type": "boolean", "description": "Start as a canary instead of full activation."},
                    "reason": {"type": "string", "description": "Optional reason recorded with the review."},
                },
                "required": ["skill_id", "version"],
                "additionalProperties": False,
            },
            handler=skill_version_activate_handler,
            permission="write",
            risk="low",
            effect="write",
            timeout_ms=30_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_learning_set",
            description=(
                "Turn automatic skill-candidate learning on or off by setting "
                "`skill_learning_mode` to off, ask_before_saving or "
                "automatic_selective. It never enables or promotes a skill. Requires "
                "an operator approval."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": list(LEARNING_MODES),
                        "description": "The skill-learning mode.",
                    },
                },
                "required": ["mode"],
                "additionalProperties": False,
            },
            handler=skill_learning_set_handler,
            permission="write",
            risk="low",
            effect="write",
            timeout_ms=10_000,
        )
    )


# ── the effect authorizer ─────────────────────────────────────────────────────


def make_skill_lifecycle_authorizer(inner: Any = None):
    """Gate the two lifecycle writes on a single-use, digest-bound approval.

    `skill_version_activate` is bound to the skill id + version (+ canary);
    `skill_learning_set` to the requested mode. Every other tool falls through.
    """

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name not in LIFECYCLE_TOOLS:
            return bool(await inner(tool, args, ctx)) if inner is not None else False

        run_args = args or {}
        if name == "skill_version_evaluate":
            subject = str(run_args.get("skill_id") or "").strip()
            version = str(run_args.get("version") or "").strip()
            if not subject or not version:
                return False
            body = version
            summary = f"Evaluate skill {subject!r} version {version}"
        elif name == "skill_version_activate":
            subject = str(run_args.get("skill_id") or "").strip()
            version = str(run_args.get("version") or "").strip()
            if not subject or not version:
                return False
            body = f"{version}\x00canary={bool(run_args.get('canary'))}"
            summary = f"Activate skill {subject!r} version {version}"
        else:
            subject = "skill_learning"
            mode = str(run_args.get("mode") or "").strip()
            if mode not in LEARNING_MODES:
                return False
            body = mode
            summary = f"Set skill learning mode to {mode!r}"

        digest = _digest(name, subject, body)
        approvals = getattr(ctx, "approvals", None) if ctx is not None else None
        if approvals is None:
            return False
        if ctx is not None and getattr(ctx, "effect_authorized_digest", None) == digest:
            return True

        claimed = approvals.consume_kind(kind=name, request_key="skill_lifecycle", digest=digest)
        if claimed is not None:
            try:
                ctx.effect_authorized_digest = digest  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass
            return True

        pending = None
        try:
            pending = approvals.request_kind(
                kind=name, request_key="skill_lifecycle", digest=digest,
                effect="write",
                run_id=str(getattr(ctx, "run_id", "")),
                action_summary=summary,
                risk="low",
            )
        except Exception:  # noqa: BLE001 - a store failure must never authorize
            return False

        emitter = getattr(ctx, "emitter", None)
        if emitter is not None:
            try:
                await emitter.emit("approval.requested", {
                    "approvalId": (pending or {}).get("id"),
                    "kind": name,
                    "title": "Approve a skill lifecycle change",
                    "summary": summary,
                    "effect": "write",
                    "risk": "low",
                    "skillId": subject,
                })
            except Exception:  # noqa: BLE001 - the card is best-effort
                pass

        if pending is not None:
            from ..mcp.approvals import pause_for_decision  # noqa: PLC0415

            if await pause_for_decision(
                approvals, ctx, pending.get("id"),
                lambda: approvals.consume_kind(kind=name, request_key="skill_lifecycle", digest=digest),
                emitter=emitter, digest=digest,
                event_type="approval.approved",
                approved_payload={"kind": name, "skillId": subject},
            ):
                return True
        return False

    return authorize


__all__ = [
    "LEARNING_MODES",
    "LIFECYCLE_TOOLS",
    "make_skill_lifecycle_authorizer",
    "register_skill_lifecycle_tools",
    "skill_learning_set_handler",
    "skill_learning_get_handler",
    "skill_reviews_handler",
    "skill_version_activate_handler",
    "skill_version_evaluate_handler",
    "skill_version_history_handler",
]
