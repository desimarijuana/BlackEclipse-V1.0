#!/usr/bin/env node
/**
 * Find and (only with --apply) delete the git refs that still expose
 * pre-rewrite history: branches whose history contains a committed database
 * snapshot or a personal author address.
 *
 * `check:oss` names the refs; this turns that list into one reviewed command
 * and refuses to touch `main`, tags, or the branch you have checked out.
 *
 * Usage (from Black-Eclipse-site/):
 *   npm run oss:prune-refs           # dry run: list refs + the command
 *   npm run oss:prune-refs -- --apply
 *   node scripts/prune-stale-refs.js --json
 */
'use strict';

const { execFileSync } = require('child_process');
const path = require('path');

const siteRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(siteRoot, '..');
const asJson = process.argv.includes('--json');
const apply = process.argv.includes('--apply');

function git(args, options = {}) {
  return execFileSync('git', args, {
    cwd: repoRoot,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
    ...options,
  });
}

function safeGit(args) {
  try {
    return git(args);
  } catch {
    return '';
  }
}

function lines(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

const bags = [
  ...new Set(
    lines(
      safeGit(['log', '--all', '--format=', '--name-only', '--diff-filter=A'])
    ).filter((file) => /(^|\/).*\.db$/i.test(file))
  ),
];

const personalEmail = (email) =>
  email &&
  !/@users\.noreply\.github\.com$/i.test(email) &&
  !/@blackeclipse\.com$/i.test(email) &&
  !/\[bot\]@/i.test(email);

const authors = new Set(lines(safeGit(['log', '--all', '--format=%ae'])).filter(personalEmail));

function staleReasons(ref) {
  const reasons = [];
  if (bags.length) {
    const hit = safeGit(['log', ref, '-1', '--format=%H', '--', ...bags]).trim();
    if (hit) reasons.push('database snapshot');
  }
  if (authors.size) {
    const found = lines(safeGit(['log', ref, '--format=%ae'])).filter((email) =>
      authors.has(email)
    );
    if (found.length) reasons.push(`personal author (${[...new Set(found)].join(', ')})`);
  }
  return reasons;
}

const main = 'main';
const current = safeGit(['rev-parse', '--abbrev-ref', 'HEAD']).trim();

const remoteBranches = lines(
  safeGit(['for-each-ref', '--format=%(refname:short)', 'refs/remotes'])
)
  .filter((ref) => !ref.endsWith('/HEAD'))
  .filter((ref) => ref !== `origin/${main}`)
  .map((ref) => ({ ref, name: ref.replace(/^origin\//, '') }));

const localBranches = lines(safeGit(['for-each-ref', '--format=%(refname:short)', 'refs/heads']))
  .filter((ref) => ref !== main && ref !== current)
  .map((ref) => ({ ref, name: ref }));

const tags = lines(safeGit(['for-each-ref', '--format=%(refname:short)', 'refs/tags']));

const staleRemote = remoteBranches
  .map((branch) => ({ ...branch, reasons: staleReasons(branch.ref) }))
  .filter((branch) => branch.reasons.length > 0);
const staleLocal = localBranches
  .map((branch) => ({ ...branch, reasons: staleReasons(branch.ref) }))
  .filter((branch) => branch.reasons.length > 0);
const staleTags = tags
  .map((tag) => ({ tag, reasons: staleReasons(tag) }))
  .filter((entry) => entry.reasons.length > 0);

const mainClean = staleReasons(main).length === 0;

if (asJson) {
  console.log(
    JSON.stringify(
      {
        apply,
        main: { clean: mainClean },
        bags,
        personalAuthors: [...authors],
        remote: staleRemote,
        local: staleLocal,
        tags: staleTags,
      },
      null,
      2
    )
  );
  process.exit(staleTags.length ? 1 : 0);
}

console.log(`[oss-refs] database paths in history: ${bags.length ? bags.join(', ') : 'none'}`);
console.log(`[oss-refs] personal authors in history: ${authors.size ? [...authors].join(', ') : 'none'}`);
console.log(`[oss-refs] main: ${mainClean ? 'clean' : 'STALE (do not delete automatically)'}`);
console.log('');

if (!staleRemote.length && !staleLocal.length && !staleTags.length) {
  console.log('[oss-refs] no stale refs - nothing to prune.');
  process.exit(0);
}

if (staleRemote.length) {
  console.log(`Stale remote branches (${staleRemote.length}):`);
  for (const branch of staleRemote) {
    console.log(`  ${branch.ref}  — ${branch.reasons.join('; ')}`);
  }
  console.log('');
}

if (staleLocal.length) {
  console.log(`Stale local branches (${staleLocal.length}):`);
  for (const branch of staleLocal) {
    console.log(`  ${branch.ref}  — ${branch.reasons.join('; ')}`);
  }
  console.log('');
}

if (staleTags.length) {
  console.log(`Tags with stale history (${staleTags.length}) - NOT deleted automatically:`);
  for (const entry of staleTags) {
    console.log(`  ${entry.tag}  — ${entry.reasons.join('; ')}`);
  }
  console.log('  Re-create the tags on the rewritten commits instead of deleting them silently.');
  console.log('');
}

const remoteNames = staleRemote.map((branch) => branch.name);
const localNames = staleLocal.map((branch) => branch.name);

if (!apply) {
  console.log('[oss-refs] dry run. No refs were changed.');
  if (remoteNames.length) {
    console.log(`  git push origin --delete ${remoteNames.join(' ')}`);
  }
  if (localNames.length) {
    console.log(`  git branch -D ${localNames.join(' ')}`);
  }
  console.log('  Re-run with --apply to execute the commands above, then `git fetch --prune`.');
  console.log('  Cached pull-request objects can still reach old commits; if a');
  console.log('  gitleaks scan of a fresh clone is not clean, publish from a new repository.');
  process.exit(staleTags.length ? 1 : 0);
}

if (staleTags.length) {
  console.error('[oss-refs] refusing to apply while stale tags exist. Re-create them first.');
  process.exit(1);
}

if (remoteNames.length) {
  console.log(`[oss-refs] deleting ${remoteNames.length} remote branch(es)…`);
  git(['push', 'origin', '--delete', ...remoteNames], { stdio: 'inherit' });
}
if (localNames.length) {
  console.log(`[oss-refs] deleting ${localNames.length} local branch(es)…`);
  git(['branch', '-D', ...localNames], { stdio: 'inherit' });
}
console.log('[oss-refs] pruning remote-tracking refs…');
git(['fetch', '--prune'], { stdio: 'inherit' });
console.log('[oss-refs] done. Run `npm run check:oss` to confirm the blocker is gone.');
