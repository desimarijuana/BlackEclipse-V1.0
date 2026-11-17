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
    // execFileSync inherits stderr by default, which leaked git's own "fatal:"
    // lines while probing ancestry of objects that are not fetched yet.
    stdio: ['ignore', 'pipe', 'pipe'],
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

// ---------------------------------------------------------------------------
// Remote pull-request refs.
//
// GitHub keeps `refs/pull/N/head` forever — including for closed, squash-merged
// and Dependabot PRs — and serves them to anyone who can read the repository.
// They are invisible to `git log --all` and to `for-each-ref refs/remotes`, so a
// branch-only audit reports "clean" while the old history is still fetchable.
// That is the exact gap that made a history rewrite look finished when it was
// not.
//
// A PR head is only interesting when it is NOT an ancestor of a live ref: if the
// commits are still on a branch or tag, that ref already accounts for them.
// ---------------------------------------------------------------------------
const BANNED_PATH =
  /(^|\/)(\.env(\.[^/]+)?|\.connector-key|mcp-servers\.json|.*\.(db|db-wal|db-shm|pem|pfx|key|p12))$/i;
const ALLOWED_PATH = /\.env\.example$/i;

const pullNamespace = 'refs/oss-preflight/pull';
const includeRemote = !process.argv.includes('--no-remote');

function remoteTips() {
  // Throws when the remote cannot be read: "could not check" must never look
  // like "nothing to find".
  return lines(
    git(['ls-remote', 'origin', 'refs/heads/*', 'refs/tags/*', 'refs/pull/*/head']).replace(
      /\r/g,
      ''
    )
  ).map((line) => {
    const [sha, name] = line.split('\t');
    return { sha, name };
  });
}

function pruneTempRefs() {
  for (const ref of lines(
    safeGit(['for-each-ref', '--format=%(refname)', pullNamespace])
  )) {
    safeGit(['update-ref', '-d', ref]);
  }
}

function prRefReasons(ref) {
  // Only banned paths block a PR ref. A contributor's commit author address is
  // their own choice and is public on GitHub anyway; treating it as a leak would
  // make the gate reject every outside pull request. It is reported separately
  // as a warning.
  const reasons = [];
  for (const line of lines(safeGit(['rev-list', ref, '--objects']))) {
    const tab = line.indexOf(' ');
    if (tab === -1) continue;
    const file = line.slice(tab + 1);
    if (ALLOWED_PATH.test(file)) continue;
    if (BANNED_PATH.test(file)) {
      reasons.push(`banned path: ${file}`);
      break;
    }
  }
  return reasons;
}

function personalAuthorsIn(ref) {
  return [
    ...new Set(
      lines(safeGit(['log', ref, '--format=%ae']))
        .map((email) => email.trim())
        .filter(personalEmail)
    ),
  ];
}

const prRefs = [];
const prPersonalAuthors = [];
let remoteChecked = false;
if (includeRemote) {
  let tips = [];
  try {
    tips = remoteTips();
    remoteChecked = true;
  } catch {
    // Leave remoteChecked false so the caller can say "not checked" instead of
    // reading an empty list as "clean".
    tips = [];
  }
  const live = tips
    .filter((tip) => !tip.name.startsWith('refs/pull/'))
    .map((tip) => tip.sha);
  const pulls = tips.filter((tip) => tip.name.startsWith('refs/pull/'));
  const isAncestor = (a, b) => {
    try {
      git(['merge-base', '--is-ancestor', a, b]);
      return true;
    } catch {
      return false;
    }
  };
  const orphans = pulls.filter((pull) => !live.some((tip) => isAncestor(pull.sha, tip)));
  for (const orphan of orphans) {
    const number = orphan.name.match(/^refs\/pull\/(\d+)\//);
    const local = `${pullNamespace}/${number ? number[1] : 'x'}`;
    try {
      safeGit(['fetch', '--no-tags', '--quiet', 'origin', `+${orphan.name}:${local}`]);
      const reasons = prRefReasons(local);
      if (reasons.length) {
        prRefs.push({
          ref: orphan.name,
          pr: number ? `#${number[1]}` : orphan.name,
          head: orphan.sha,
          reasons,
        });
      }
      const emails = personalAuthorsIn(local);
      if (emails.length) {
        prPersonalAuthors.push({
          ref: orphan.name,
          pr: number ? `#${number[1]}` : orphan.name,
          emails,
        });
      }
    } catch {
      prRefs.push({
        ref: orphan.name,
        pr: number ? `#${number[1]}` : orphan.name,
        head: orphan.sha,
        reasons: ['could not fetch to inspect'],
      });
    }
  }
  pruneTempRefs();
}

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
        pullRequests: prRefs,
        pullRequestPersonalAuthors: prPersonalAuthors,
        remoteChecked,
      },
      null,
      2
    )
  );
  process.exit(staleTags.length || prRefs.length ? 1 : 0);
}

console.log(`[oss-refs] database paths in history: ${bags.length ? bags.join(', ') : 'none'}`);
console.log(`[oss-refs] personal authors in history: ${authors.size ? [...authors].join(', ') : 'none'}`);
console.log(`[oss-refs] main: ${mainClean ? 'clean' : 'STALE (do not delete automatically)'}`);
console.log('');

if (
  !staleRemote.length &&
  !staleLocal.length &&
  !staleTags.length &&
  !prRefs.length &&
  !prPersonalAuthors.length
) {
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

if (prRefs.length) {
  console.log(`Pull-request refs that still reach old history (${prRefs.length}):`);
  for (const pr of prRefs) {
    console.log(`  ${pr.ref} (${pr.pr})  — ${pr.reasons.join('; ')}`);
  }
  console.log('  These CANNOT be removed with `git push origin --delete`: GitHub manages');
  console.log('  refs/pull/* itself and keeps them for every closed/merged PR. Publish from');
  console.log('  a freshly created repository, or ask GitHub Support to purge the objects.');
  console.log('');
}

if (prPersonalAuthors.length) {
  console.log(`Pull-request refs by a non-noreply author (${prPersonalAuthors.length}) - warning only:`);
  for (const entry of prPersonalAuthors) {
    console.log(`  ${entry.ref} (${entry.pr})  — ${entry.emails.join(', ')}`);
  }
  console.log('  A contributor chooses their own commit address and GitHub shows it anyway,');
  console.log('  so this is reported, not blocked. It matters only for this project\'s own refs.');
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
  process.exit(staleTags.length || prRefs.length ? 1 : 0);
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

if (prRefs.length) {
  console.error(
    `[oss-refs] branches pruned, but ${prRefs.length} pull-request ref(s) still reach old history. ` +
      'Those are server-managed: publish from a new repository or ask GitHub Support to purge. `check:oss` stays red until then.'
  );
  process.exit(1);
}

console.log('[oss-refs] done. Run `npm run check:oss` to confirm the blocker is gone.');
