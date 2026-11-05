// ── Seed the Graph Studio files/media demo ──────────────────────────────────
// Creates (idempotently) two demo workflows in Overview:
//   * "File import (demo)" — the generated CSV -> parse -> select -> result.
//   * "Candle option review (demo)" — two generated candle images -> vision
//     batch -> agent task -> result.
//
// The sample assets are created through the SAME runtime stores the nodes use
// (graph asset store + vision asset store), so the demo runs against real local
// data. The image workflow still needs a configured vision model, exactly like
// a real image node.
//
// Run: npm run demo:graph-media
//
// Nothing here is committed as binary data; the helper regenerates the CSV and
// two deterministic PNGs, then prints their refs.

import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';
import { buildTemplate } from '../src/lib/graph-studio/templates';
import { requiredCapabilitiesFor } from '../src/lib/graph-studio/validation';
import {
  createWorkflow,
  listWorkflows,
} from '../src/lib/graph-studio/server-store';
import type { WorkflowIR } from '../src/lib/graph-studio/types';

const require = createRequire(import.meta.url);
const { pythonDir, pythonPathEnv, resolvePython } = require('./python-runner.js') as {
  pythonDir: string;
  pythonPathEnv: () => string;
  resolvePython: (probe?: string) => string | null;
};

interface DemoAssets {
  fileAssetId: string;
  fileRef: string;
  fileName: string;
  imageAssetIds: string[];
}

function createAssets(): DemoAssets {
  const python = resolvePython('import PIL');
  if (!python) {
    throw new Error('The Python runtime with Pillow is unavailable. Run: npm run setup:python');
  }
  const result = spawnSync(
    python,
    [path.join('scripts', 'seed_graph_media_demo.py')],
    {
      cwd: pythonDir,
      env: { ...process.env, PYTHONPATH: pythonPathEnv() },
      encoding: 'utf8',
      timeout: 120_000,
    },
  );
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || 'asset seeding failed');
  }
  const line = result.stdout.trim().split(/\r?\n/).filter(Boolean).pop() ?? '';
  const parsed = JSON.parse(line) as DemoAssets;
  if (!parsed.fileAssetId || parsed.imageAssetIds.length < 2) {
    throw new Error('asset seeding returned no usable refs');
  }
  return parsed;
}

function withNodeConfig(
  ir: WorkflowIR,
  type: string,
  patch: Record<string, unknown>,
): WorkflowIR {
  return {
    ...ir,
    nodes: ir.nodes.map((node) =>
      node.type === type
        ? { ...node, config: { ...node.config, ...patch } }
        : node,
    ),
  };
}

function fileDemo(assets: DemoAssets): WorkflowIR {
  const ir = buildTemplate('file-import');
  if (!ir) throw new Error('file-import template is missing');
  return withNodeConfig(ir, 'data.file.attach', { assetId: assets.fileAssetId });
}

function candleDemo(assets: DemoAssets): WorkflowIR {
  const base = buildTemplate('candle-review');
  if (!base) throw new Error('candle-review template is missing');
  // The seeded demo proves the VISION path end-to-end. The review template keeps
  // the agent node for users whose chat model is configured; the demo does not
  // depend on a second (text) model call.
  const nodes = base.nodes
    .filter((node) => node.id !== 'agent')
    .map((node) => node.id === 'result'
      ? { ...node, label: 'Image readings', config: { ...node.config, label: 'Image readings' } }
      : node);
  const edges = base.edges
    .filter((edge) => edge.source !== 'agent' && edge.target !== 'agent')
    .concat({
      id: 'e-image-readings',
      source: 'batch',
      sourceHandle: 'results',
      target: 'result',
      targetHandle: 'value',
    });
  const ir: WorkflowIR = {
    ...base,
    description: 'Read two candle images through the vision API and return the readings.',
    nodes,
    edges,
  };
  ir.requiredCapabilities = requiredCapabilitiesFor(ir);
  return withNodeConfig(ir, 'image.batch', {
    assetIds: JSON.stringify(assets.imageAssetIds),
    questionsJson: JSON.stringify([
      'Describe each candle in the image (body, wicks, direction).',
      'What pattern is this and what would confirm it?',
    ]),
  });
}

async function ensureWorkflow(
  name: string,
  ir: WorkflowIR,
  tags: string[],
): Promise<string> {
  const existing = (await listWorkflows({ includeArchived: true }))
    .find((item) => item.name === name);
  const next = { ...ir, name };
  if (!existing) {
    const created = await createWorkflow({ name, description: ir.description, ir: next, tags });
    console.log(`create ${name} (${created.id}, v${created.version})`);
    return created.id;
  }
  // The demo is seeded, not editor-authored. Reuse it on every run so the
  // gallery does not accumulate versions; delete it to regenerate from scratch.
  console.log(`reuse  ${name} (${existing.id}, v${existing.currentVersion})`);
  return existing.id;
}

async function main(): Promise<void> {
  const assets = createAssets();
  console.log(`asset  ${assets.fileName} -> ${assets.fileAssetId}`);
  console.log(`asset  ${assets.imageAssetIds.length} candle image(s)`);
  const fileId = await ensureWorkflow(
    'File import (demo)',
    fileDemo(assets),
    ['demo', 'files', 'data'],
  );
  const candleId = await ensureWorkflow(
    'Candle option review (demo)',
    candleDemo(assets),
    ['demo', 'images', 'trading'],
  );
  console.log(JSON.stringify({ fileWorkflowId: fileId, candleWorkflowId: candleId }));
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
