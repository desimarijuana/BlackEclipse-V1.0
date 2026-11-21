// The domain-aware release gate: run the FULL suite for each area you changed,
// and nothing for areas you did not.
//
// WHY this exists: `npm run test` always runs vitest (554 files), the Python
// suite (1017 files) and the eval floors, no matter what changed. Measured here:
// vitest ~158s, Python ~953s, evals ~226s - so a one-line UI edit pays ~22
// minutes, 80% of it for a runtime it cannot possibly have touched.
//
// This is NOT the partial fast lane (`npm run test:fast`, which skips tests that
// merely *import* what you changed). Every domain this runs is run COMPLETE, so
// a green `verify` means the affected subsystem is fully green. What it drops is
// only the work in domains your change never entered.
//
// Usage:
//   npm run verify            # run the domains implied by the working tree
//   npm run verify -- --all   # force every domain (same as `npm run test`)
//   BE_TEST_WORKERS=2 npm run verify
const { spawnSync } = require('child_process');
const path = require('path');
const { changedFiles, under } = require('./lib/changed-files');

const root = path.join(__dirname, '..');

const run = (label, cmd, args, env) => {
  console.log(`\n[verify] ${label}`);
  const result = spawnSync(cmd, args, {
    cwd: root,
    stdio: 'inherit',
    shell: process.platform === 'win32',
    env: { ...process.env, ...env },
  });
  if ((result.status ?? 1) !== 0) {
    console.error(`[verify] FAILED: ${label}`);
    process.exit(result.status ?? 1);
  }
};

const all = process.argv.includes('--all');
const changed = changedFiles();

// Without git the changed set is unknowable, so everything runs: a gate must
// never report success by assuming nothing was touched.
if (!changed.ok) {
  console.log(`[verify] ${changed.reason} - running every domain.`);
}

const files = all || !changed.ok ? null : changed.files;
const touches = (prefix, ...exts) => (files === null ? true : under(files, prefix, ...exts).length > 0);

const ts = touches('src/', '.ts', '.tsx');
const py = touches('python/', '.py');
// The eval floors grade the memory subsystem; a change elsewhere in python/ does
// not move them, and they cost ~4 minutes.
const memory = touches('python/harness/eclipse_memory/', '.py');

if (!ts && !py) {
  console.log('[verify] no src/ or python/ changes - typecheck only.');
  console.log('[verify] (docs, scripts and config changes are covered by `npm run lint` and reviewers.)');
}

// Always: it costs 16s and catches the type ripples no test imports.
run('typecheck', 'npx', ['tsc', '--noEmit']);

if (ts) run('vitest (full)', 'npx', ['vitest', 'run']);
if (py) run('python suite (full)', 'node', ['scripts/test-python.js']);
if (memory) run('eval floors', 'node', ['scripts/test-evals.js']);

console.log('\n[verify] all affected domains passed.');
