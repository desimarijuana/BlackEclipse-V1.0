// Run the Eclipse-Memory evaluation gates locally, the same way CI must.
//
// WHY: the release gates (retrieval, contradiction, compaction) were only
// referenced by a workflow that GitHub never reads, so a local regression was
// invisible. This makes them one honest `npm run test:evals` command.
//
// It uses the same interpreter the runtime uses and the same explicit-sys.path
// launcher pattern as scripts/test-python.js, because the vendored interpreter's
// `python312._pth` disables implicit sys.path[0] and ignores both cwd and
// PYTHONPATH — so `python -m harness.eval...` cannot resolve the package there.
//
// Each gate exits non-zero on a floor violation, so this command fails a broken
// floor. The three surviving gates are retrieval, contradiction and compaction;
// the semantic gate was deleted deliberately (its `semantic_cli` module is gone),
// so it is not referenced here.
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const pythonDir = path.join(root, "python");
const vendored = path.join(__dirname, "vendor", "python", "python.exe");

const candidates =
  process.platform === "win32"
    ? [fs.existsSync(vendored) ? vendored : null, "python", "python3", "py"].filter(Boolean)
    : ["python3", "python"];

function tryRun(cmd, args) {
  try {
    return spawnSync(cmd, args, { stdio: "ignore" });
  } catch {
    return { status: 1 };
  }
}

const isPath = (c) => c.includes(path.sep) || c.endsWith(".exe");
const usable = (cmd) =>
  tryRun(cmd, ["--version"]).status === 0 &&
  tryRun(cmd, ["-c", "import langgraph, pytest"]).status === 0;
const py = candidates.find((c) => usable(isPath(c) ? c : c));
if (!py) {
  console.log("[evals] Python agent stack not installed — skipping eval gates.");
  console.log("[evals] Install it with: npm run setup:python");
  process.exit(0);
}

// The three gates, in order. Each returns an exit code; any non-zero fails the
// command. The launcher injects `python/` onto sys.path so it works identically
// for the vendored and system interpreters.
const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  "from harness.eclipse_memory.eval import run_evaluation, check_thresholds, format_report",
  "from harness.eclipse_memory.eval.contradictions import (",
  "    run_contradiction_evaluation, check_contradiction_thresholds, format_contradiction_report",
  ")",
  "from harness.eclipse_memory.eval.compaction import (",
  "    run_compaction_eval, check_compaction_thresholds",
  ")",
  "failed = []",
  "rep = run_evaluation()",
  "print(format_report(rep))",
  "g = check_thresholds(rep)",
  "print('  retrieval gate:', 'PASS' if g['passed'] else 'FAIL', g['failures'] if not g['passed'] else '')",
  "failed += [] if g['passed'] else ['retrieval']",
  "crep = run_contradiction_evaluation()",
  "print(format_contradiction_report(crep))",
  "cg = check_contradiction_thresholds(crep)",
  "print('  contradiction gate:', 'PASS' if cg['passed'] else 'FAIL', cg['failures'] if not cg['passed'] else '')",
  "failed += [] if cg['passed'] else ['contradiction']",
  "comp = check_compaction_thresholds(run_compaction_eval())",
  "print('  compaction gate:', 'PASS' if comp['passed'] else 'FAIL', comp['failures'] if not comp['passed'] else '')",
  "failed += [] if comp['passed'] else ['compaction']",
  // Phase 4: the code-verification floor (falseVerifiedRate must be 0).
  "from harness.code.eval import run_evaluation as run_code_eval, check_thresholds as check_code_thresholds, format_report as format_code_report",
  "cv = run_code_eval()",
  "print('  ' + format_code_report(cv).splitlines()[0])",
  "cg = check_code_thresholds(cv)",
  "print('  code_verify gate:', 'PASS' if cg['passed'] else 'FAIL', cg['failures'] if not cg['passed'] else '')",
  "failed += [] if cg['passed'] else ['code_verify']",
  // Phase 12: the code task + safety floor (per-shape, never a blended score).
  "from harness.code.eval import run_code_evaluation, check_code_thresholds as check_code_gate, format_code_report",
  "cc = run_code_evaluation()",
  "print('  ' + format_code_report(cc).splitlines()[1])",
  "print('  safety:', ', '.join(c.caseId.split('-')[0] + '=' + ('PASS' if c.passed else 'FAIL') for c in cc['safety']))",
  "ccg = check_code_gate(cc)",
  "print('  code gate:', 'PASS' if ccg['passed'] else 'FAIL', ccg['failures'] if not ccg['passed'] else '')",
  "failed += [] if ccg['passed'] else ['code']",
  // Unified search: the offline retrieval-quality floor (keyword path).
  "from harness.search.eval_gate import run_search_eval, check_search_thresholds, format_search_report",
  "srep = run_search_eval()",
  "print('  ' + format_search_report(srep))",
  "sg = check_search_thresholds(srep)",
  "print('  search gate:', 'PASS' if sg['passed'] else 'FAIL', sg['failures'] if not sg['passed'] else '')",
  "failed += [] if sg['passed'] else ['search']",
  // Harness closeout Phase 8: the capability-matrix gate is TS (invoked by
  // run_gates via npx tsx); route_health/workflow/resume are Python. All offline.
  "from harness.eval_gates import run_gates",
  "for g in run_gates():",
  "    print('  ' + g['name'] + ' gate:', 'PASS' if g['passed'] else 'FAIL', g['failures'] if not g['passed'] else '')",
  "    failed += [] if g['passed'] else [g['name']]",
  // Agent Evaluation system (offline tier): runs the real runtime against the
  // deterministic benchmark on a PRIVATE temp DB and gates on the safety /
  // hallucination / refusal floors. Per-category, never a blended score.
  "from harness.evaluation.gate import run_offline_gate, format_gate_report",
  "_es = run_offline_gate()",
  "[print('  ' + l) for l in format_gate_report(_es)]",
  "failed += [] if _es.passed else ['evaluation']",
  // R3-08: the construction benchmark — the 16 master-plan scenarios, graded
  // through the same real runtime. It is inside the merged gate above; this
  // line pins it as its own named gate so the construction floor can never be
  // dropped from the chain silently.
  "from harness.evaluation.gate import run_offline_gate as run_construction_gate",
  "_cs = run_construction_gate(dataset_name='construction_v1')",
  "print('  construction gate:', 'PASS' if _cs.passed else 'FAIL', 'tasks=' + str(len(_cs.tasks)), 'task_success=' + str(_cs.aggregates.get('task_success')), 'recovery_success=' + str(_cs.aggregates.get('recovery_success')))",
  "failed += [] if _cs.passed else ['construction']",
  // Phase 20 (ADR-H193): the capability-class gate — every registered class is
  // measured or NAMED as not measured; a measured class may not regress.
  "from harness.code.eval.capabilities import run_capability_eval, check_capability_floors",
  "_cap = run_capability_eval()",
  "_capv = check_capability_floors(_cap)",
  "print('  capability-class gate:', 'PASS' if _capv['passed'] else 'FAIL', 'measured=' + str(_capv['measured']), 'unmeasured=' + str(_capv['unmeasured']), _capv['failures'] if not _capv['passed'] else '')",
  "failed += [] if _capv['passed'] else ['capability_classes']",
  "print('eval gates:', 'ALL PASS' if not failed else 'FAILED: ' + ','.join(failed))",
  "sys.exit(0 if not failed else 1)",
].join("\n");

console.log("[evals] Running Eclipse-Memory eval gates (offline)…");
const result = spawnSync(py, ["-c", launcher], { stdio: "inherit", cwd: pythonDir });
process.exit(result.status ?? 1);
