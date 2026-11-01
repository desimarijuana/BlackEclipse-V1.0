// ── Graph Studio loop demo: build the IR, verify it, persist it ──────────────
// Creates TWO real workflows in JDDS:
//
//   1. "Loop body — 7% growth step"  the pinned body every loop node calls.
//      trigger → formula (x * 1.07) → result
//
//   2. "Compounding planner (loops)" the parent. One branch per loop shape:
//        · flow.repeat  — 12-year fixed horizon, then an if/else on the target
//        · flow.while   — run until the balance reaches 2000
//        · flow.for_each— project three principals one year each
//
// Why one body: all three loops want the same "one period of growth" step, and a
// pinned body is what makes an iteration a resumable child run.
//
//   npx tsx scripts/graph-loop-demo.mts --dry    # write IR JSON only (no DB)
//   npx tsx scripts/graph-loop-demo.mts          # create the workflows in JDDS
//   npm run demo:loop                            # run the pair through the runtime

import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createWorkflowIR } from '../src/lib/graph-studio/ir';
import { autoLayout } from '../src/lib/graph-studio/layout';
import { getNodeDefinition } from '../src/lib/graph-studio/registry';
import type { WorkflowEdge, WorkflowIR, WorkflowNode } from '../src/lib/graph-studio/types';
import { requiredCapabilitiesFor, validateWorkflow } from '../src/lib/graph-studio/validation';

const BODY_ID_FOR_DRY_RUN = 'wf_loop_demo_body';
const GROWTH = 1.07;
const PRINCIPAL = 1000;
const TARGET = 2000;
const BATCH = [1000, 1500, 2000];

interface NodeSpec {
  id: string;
  type: string;
  config?: Record<string, unknown>;
  label?: string;
}

type EdgeSpec = {
  source: string;
  sourceHandle: string;
  target: string;
  targetHandle: string;
};

function buildGraph(
  name: string,
  description: string,
  nodeSpecs: NodeSpec[],
  edgeSpecs: EdgeSpec[],
): WorkflowIR {
  const nodes: WorkflowNode[] = nodeSpecs.map((spec) => {
    const def = getNodeDefinition(spec.type);
    if (!def) throw new Error(`unknown node type "${spec.type}"`);
    return {
      id: spec.id,
      type: def.type,
      version: def.version,
      label: spec.label,
      config: { ...def.defaultConfig(), ...(spec.config ?? {}) },
      layout: { x: 0, y: 0 },
    };
  });
  const edges: WorkflowEdge[] = edgeSpecs.map((spec, index) => ({ id: `e${index + 1}`, ...spec }));
  let ir = createWorkflowIR({ name, description, nodes, edges });
  const positions = autoLayout(ir);
  ir = { ...ir, nodes: ir.nodes.map((n) => ({ ...n, layout: positions[n.id] ?? n.layout })) };
  return { ...ir, requiredCapabilities: requiredCapabilitiesFor(ir) };
}

/** The pinned body: one period of growth applied to whatever balance arrives. */
export function bodyIr(): WorkflowIR {
  return buildGraph(
    'Loop body — 7% growth step',
    'Pinned body for the loop nodes: the trigger carries the balance in, the result carries it out.',
    [
      { id: 'trigger', type: 'trigger.manual', label: 'Balance in' },
      {
        id: 'grow',
        type: 'transform.formula',
        config: { expression: `x * ${GROWTH}` },
        label: 'Grow 7%',
      },
      { id: 'result', type: 'output.result', config: { label: 'Balance out' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'grow', targetHandle: 'x' },
      { source: 'grow', sourceHandle: 'result', target: 'result', targetHandle: 'value' },
    ],
  );
}

/** The parent: one branch per loop shape, all pinned to the same body version. */
export function parentIr(bodyWorkflowId: string): WorkflowIR {
  const pin = { workflowId: bodyWorkflowId, version: 1 };
  return buildGraph(
    'Compounding planner (loops)',
    'Three loop shapes over one pinned growth step: a 12-year repeat with an if/else, a goal-seeking while, and a for-each projection. No market data needed.',
    [
      { id: 'trigger', type: 'trigger.manual' },

      // ── repeat: fixed 12-year horizon, then branch on the target ──────────
      {
        id: 'principal',
        type: 'data.value',
        config: { dataType: 'number', value: String(PRINCIPAL) },
        label: 'Principal',
      },
      {
        id: 'repeat',
        type: 'flow.repeat',
        config: { ...pin, count: 12 },
        label: '12 years',
      },
      {
        id: 'target',
        type: 'logic.condition',
        config: { operator: 'gt', compareTo: String(TARGET) },
        label: `Above ${TARGET}?`,
      },
      { id: 'metGate', type: 'flow.gate', label: 'Target met' },
      { id: 'missGate', type: 'flow.gate', label: 'Below target' },
      {
        id: 'metText',
        type: 'transform.template',
        config: { template: `12 years: {{a:.2f}} — target met` },
        label: 'Met',
      },
      {
        id: 'missText',
        type: 'transform.template',
        config: { template: `12 years: {{a:.2f}} — below target` },
        label: 'Missed',
      },
      { id: 'metOut', type: 'output.result', config: { label: 'Repeat · met' } },
      { id: 'missOut', type: 'output.result', config: { label: 'Repeat · below' } },

      // ── while: run until the balance reaches the target ───────────────────
      {
        id: 'startBalance',
        type: 'data.value',
        config: { dataType: 'number', value: String(PRINCIPAL) },
        label: 'Start',
      },
      {
        id: 'while',
        type: 'flow.while',
        config: { ...pin, condition: `value < ${TARGET}`, maxIterations: 100 },
        label: `Until ${TARGET}`,
      },
      {
        id: 'whileText',
        type: 'transform.template',
        config: { template: `Reached {{a:.2f}} after {{b}} year(s)` },
        label: 'Goal',
      },
      { id: 'whileOut', type: 'output.result', config: { label: 'While · goal' } },

      // ── for_each: one iteration per principal ────────────────────────────
      {
        id: 'batch',
        type: 'data.value',
        config: { dataType: 'string', value: JSON.stringify(BATCH) },
        label: 'Principals',
      },
      { id: 'parse', type: 'data.json.parse', label: 'Parse' },
      {
        id: 'each',
        type: 'flow.for_each',
        config: { ...pin, maxIterations: 10 },
        label: 'Per principal',
      },
      {
        id: 'eachText',
        type: 'transform.template',
        config: { template: `After one year: {{#each a}}{{this:.2f}} {{/each}}` },
        label: 'Projection',
      },
      { id: 'eachOut', type: 'output.result', config: { label: 'For each · projection' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'principal', targetHandle: 'in' },
      { source: 'principal', sourceHandle: 'value', target: 'repeat', targetHandle: 'input' },
      { source: 'repeat', sourceHandle: 'state', target: 'target', targetHandle: 'value' },
      { source: 'target', sourceHandle: 'true', target: 'metGate', targetHandle: 'in' },
      { source: 'repeat', sourceHandle: 'state', target: 'metGate', targetHandle: 'value' },
      { source: 'metGate', sourceHandle: 'value', target: 'metText', targetHandle: 'a' },
      { source: 'metText', sourceHandle: 'text', target: 'metOut', targetHandle: 'value' },
      { source: 'target', sourceHandle: 'false', target: 'missGate', targetHandle: 'in' },
      { source: 'repeat', sourceHandle: 'state', target: 'missGate', targetHandle: 'value' },
      { source: 'missGate', sourceHandle: 'value', target: 'missText', targetHandle: 'a' },
      { source: 'missText', sourceHandle: 'text', target: 'missOut', targetHandle: 'value' },

      { source: 'trigger', sourceHandle: 'start', target: 'startBalance', targetHandle: 'in' },
      { source: 'startBalance', sourceHandle: 'value', target: 'while', targetHandle: 'input' },
      { source: 'while', sourceHandle: 'state', target: 'whileText', targetHandle: 'a' },
      { source: 'while', sourceHandle: 'iterations', target: 'whileText', targetHandle: 'b' },
      { source: 'whileText', sourceHandle: 'text', target: 'whileOut', targetHandle: 'value' },

      { source: 'trigger', sourceHandle: 'start', target: 'batch', targetHandle: 'in' },
      { source: 'batch', sourceHandle: 'value', target: 'parse', targetHandle: 'text' },
      { source: 'parse', sourceHandle: 'value', target: 'each', targetHandle: 'items' },
      { source: 'each', sourceHandle: 'results', target: 'eachText', targetHandle: 'a' },
      { source: 'eachText', sourceHandle: 'text', target: 'eachOut', targetHandle: 'value' },

      // A transform node runs on dataflow alone while its `in` control port is
      // unwired, so the branch templates must be gated by their own gate's
      // `done` — otherwise the untaken branch runs with a null input.
      { source: 'metGate', sourceHandle: 'done', target: 'metText', targetHandle: 'in' },
      { source: 'missGate', sourceHandle: 'done', target: 'missText', targetHandle: 'in' },
    ],
  );
}

function assertValid(label: string, ir: WorkflowIR): void {
  const diagnostics = validateWorkflow(ir);
  const errors = diagnostics.filter((d) => d.severity === 'error');
  for (const warning of diagnostics.filter((d) => d.severity === 'warning')) {
    console.warn(`  warning: ${warning.code} — ${warning.message}`);
  }
  if (errors.length > 0) {
    for (const error of errors) console.error(`  error: ${error.code} — ${error.message}`);
    throw new Error(`${label} does not validate`);
  }
  console.log(`  ${label}: ${ir.nodes.length} node(s), ${ir.edges.length} edge(s), valid`);
}

async function main(): Promise<void> {
  const dryRun = process.argv.includes('--dry');
  const body = bodyIr();
  assertValid('body', body);

  if (dryRun) {
    const parent = parentIr(BODY_ID_FOR_DRY_RUN);
    assertValid('parent (dry run)', parent);
    const dir = join(process.cwd(), '.black-eclipse', 'tmp');
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'loop-body.json'), JSON.stringify(body, null, 2), 'utf8');
    writeFileSync(join(dir, 'loop-parent.json'), JSON.stringify(parent, null, 2), 'utf8');
    console.log(`  wrote ${join(dir, 'loop-body.json')}`);
    console.log(`  wrote ${join(dir, 'loop-parent.json')}`);
    return;
  }

  const { createWorkflow, listWorkflows } = await import('../src/lib/graph-studio/server-store');

  const existing = await listWorkflows({ includeArchived: true });
  const clash = existing.filter((w) => w.name === body.name || w.name.startsWith('Compounding planner'));
  if (clash.length > 0) {
    console.log('Already created:');
    for (const workflow of clash) console.log(`  ${workflow.id}  ${workflow.name}`);
    console.log('Delete them in the app (or re-run with --dry) to recreate.');
    return;
  }

  const savedBody = await createWorkflow({
    name: body.name,
    description: body.description,
    tags: ['graph-studio', 'loop', 'demo'],
    ir: body,
  });
  console.log(`  created body   ${savedBody.id}`);

  const parent = parentIr(savedBody.id);
  assertValid('parent', parent);
  const savedParent = await createWorkflow({
    name: parent.name,
    description: parent.description,
    tags: ['graph-studio', 'loop', 'demo'],
    ir: parent,
  });
  console.log(`  created parent ${savedParent.id}`);
  console.log('\nOpen Workflows → "Compounding planner (loops)" and press Start workflow.');
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  });
