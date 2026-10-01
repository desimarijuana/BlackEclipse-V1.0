"""Workflow validation (Harness closeout Phase 5).

Rejects — each with a NAMED reason — a cycle, an unbounded fan-out, a step
referencing a tool outside its declared scope, and a step with no terminal path.
Validation is deterministic and pure; it never touches the registry or the model.

`known_tools` is the set of tool names the runtime actually has. A step that
declares a tool the runtime does not have is rejected at validation time, not at
execution time — a plan that cannot run is refused before it is stored.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .model import (
    MAX_PARALLEL_FANOUT,
    MAX_STEPS,
    Workflow,
    WorkflowValidationError,
)


def _detect_cycle(workflow: Workflow) -> Optional[list[str]]:
    """Return a cycle (list of step ids) if the dependency graph has one."""
    edges: dict[str, list[str]] = {s.id: list(s.depends_on) for s in workflow.steps}
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in edges}
    stack: list[str] = []

    def visit(node: str) -> Optional[list[str]]:
        color[node] = GREY
        stack.append(node)
        for dep in edges.get(node, []):
            if dep not in edges:
                continue
            if color[dep] == GREY:
                # Found a back-edge: the cycle is from dep to the top of the stack.
                idx = stack.index(dep)
                return stack[idx:] + [dep]
            if color[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for sid in edges:
        if color[sid] == WHITE:
            found = visit(sid)
            if found:
                return found
    return None


def _terminal_reachable(workflow: Workflow) -> bool:
    """True when every step can reach a terminal step (or is itself terminal).

    A step with no outgoing edge and `terminal=False` is a dead end — the plan has
    a path that never terminates. Rejected.
    """
    by_id = {s.id: s for s in workflow.steps}
    terminals = {s.id for s in workflow.steps if s.terminal}
    if not terminals:
        return False
    # A step's successors are its dependents plus any declared branches.
    successors: dict[str, set[str]] = {s.id: set(s.branches) for s in workflow.steps}
    for s in workflow.steps:
        for dep in s.depends_on:
            successors.setdefault(dep, set()).add(s.id)

    # Reverse-reachability from terminals: a step is fine if a terminal is
    # reachable by following successors.
    reachable_to_terminal: set[str] = set()
    changed = True
    while changed:
        changed = False
        for sid, succ in successors.items():
            if sid in reachable_to_terminal:
                continue
            if sid in terminals or any(x in reachable_to_terminal for x in succ):
                reachable_to_terminal.add(sid)
                changed = True
    return all(sid in reachable_to_terminal for sid in by_id)


def validate_workflow(
    workflow: Workflow, *, known_tools: Optional[Iterable[str]] = None,
) -> None:
    """Validate a workflow, raising `WorkflowValidationError` with a named reason.

    Checks, in order, so the first defect a caller reads is the most structural:
      1. non-empty, bounded step list (MAX_STEPS);
      2. unique step ids; dependency ids exist;
      3. no cycle;
      4. bounded fan-out for a `parallel` step;
      5. every declared tool is a real tool (out-of-scope step rejected);
      6. a reachable terminal path exists.
    """
    if not workflow.steps:
        raise WorkflowValidationError("workflow has no steps")
    if len(workflow.steps) > MAX_STEPS:
        raise WorkflowValidationError(f"workflow exceeds the {MAX_STEPS}-step bound")

    ids = [s.id for s in workflow.steps]
    if len(set(ids)) != len(ids):
        dupe = next(i for i in ids if ids.count(i) > 1)
        raise WorkflowValidationError(f"duplicate step id {dupe!r}", step_id=dupe)

    id_set = set(ids)
    for step in workflow.steps:
        for dep in step.depends_on:
            if dep not in id_set:
                raise WorkflowValidationError(
                    f"depends_on references unknown step {dep!r}", step_id=step.id,
                )
        if step.id in step.depends_on:
            raise WorkflowValidationError("step depends on itself", step_id=step.id)
        if step.kind == "parallel" and len(step.branches) > MAX_PARALLEL_FANOUT:
            raise WorkflowValidationError(
                f"parallel fan-out {len(step.branches)} exceeds the {MAX_PARALLEL_FANOUT} bound",
                step_id=step.id,
            )
        if step.kind == "conditional" and not step.condition:
            raise WorkflowValidationError("conditional step has no condition", step_id=step.id)
        if step.kind == "skill" and not step.skill_id:
            raise WorkflowValidationError("skill step has no skill_id", step_id=step.id)
        if step.kind == "approval" and not (step.approval or {}).get("tool"):
            raise WorkflowValidationError("approval step has no approval.tool", step_id=step.id)
        if step.tools is not None and known_tools is not None:
            unknown = [t for t in step.tools if t not in set(known_tools)]
            if unknown:
                raise WorkflowValidationError(
                    f"step declares unknown tool(s): {', '.join(sorted(unknown))}", step_id=step.id,
                )

    cycle = _detect_cycle(workflow)
    if cycle:
        raise WorkflowValidationError(f"dependency cycle: {' -> '.join(cycle)}")

    if not _terminal_reachable(workflow):
        raise WorkflowValidationError("workflow has no reachable terminal path")


__all__ = ["validate_workflow"]
