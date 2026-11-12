An agent that writes a beautiful answer but loses the run behind it isn't an
analyst. It's a liability.

This week we worked on exactly that in Eclipse: not a smarter model, a harness
that cannot quietly fake the work.

Round 5 - core integrity. The mechanisms, not the adjectives:

→ One durable execution plane. Every run claims a lease via BEGIN IMMEDIATE and
executes under a monotonic fencing epoch. Duplicate submissions get
RUN_LEASE_CONFLICT; terminal writes are guarded by WHERE lease_epoch = E, so a
stale worker's write is a no-op.

→ At-most-once effects. Effectful tool calls are journaled started before
dispatch and done after. If the process dies mid-call, resume sees
started-without-done, marks the outcome unknown, and makes the model reconcile
(broker terminal, git status, file hash). Read-only tools stay retryable.

→ Resume, don't replay. SSE frames carry id: <seq> and accept Last-Event-ID. A
dropped connection reconnects at the message cursor, and the client reattaches
by chat id instead of submitting a second run.

→ Claims need handles. An evidence ledger records path / run_id /
artifact_digest / record_id / citation per claim. Finance, citation, code and
artifact verifiers run at the answer seam and reject unsupported claims.

→ Capability tokens, not vibes. Effectful calls carry HMAC tokens bound to
(runId, tool, argsDigest, tenant, expiry) in shadow/enforce mode. Sandbox
profiles report enforceable=false plus the missing guarantee, and the executor
refuses instead of pretending.

→ Observability with teeth. run → step → tool/LLM spans, per-step cost from one
pricing registry (unknown model = None, never zero), five SLOs with error
budgets, and npm run gate:slo wired into CI.

Proof, reproducible from committed artifacts:
- 40/40 probe runs terminal, 0 orphaned, p95 1.885 s, $0.0007/task
- 5/5 SLOs in budget, 100% error budget remaining
- 12/12 conformance: 6 fault injections, 1 golden trace, 5 contracts
- offline harness floor: task_success 99.69, tool_accuracy 97.12, planning 89.37
- scorecard coverage: 62/100 weight measured, 38 partial - published, not hidden

The interesting part of agentic finance isn't the demo. It's whether the run
survives a kill -9, whether the number has a provenance handle, and whether the
system says "I couldn't check this" instead of inventing an answer.

Full report attached: 3 pages, lifecycle diagram, failure matrix, charts. Open
source, self-hosted, MIT.

#AgenticAI #FinTech #AIEngineering #FinancialResearch #OpenSource
