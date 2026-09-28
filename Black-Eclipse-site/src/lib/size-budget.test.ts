import { describe, expect, it } from 'vitest';
import { readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

// "Keep files small" guard (AGENTS.md). Memory is the top constraint on this
// machine, so a runaway monolith is a real risk. This is intentionally a
// GENEROUS ceiling: it does not gate today's largest files, it catches a future
// file that balloons past a maintainable size. `src/generated/` (Prisma output)
// is excluded — it is machine-written and already large by design.

// Anchor to this file's directory (…/src/lib) → repo app root, independent of
// the process cwd (which may be the workspace root, not `Black-Eclipse-site`).
const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..', '..');
const MAX_BYTES = 200 * 1024;
const SKIP_DIRS = new Set(['generated', 'node_modules', '.next', '.next-dev']);

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      walk(full, out);
    } else if (entry.name.endsWith('.ts') || entry.name.endsWith('.tsx')) {
      out.push(full);
    }
  }
  return out;
}

describe('source size budget', () => {
  it('no hand-written source file exceeds the ceiling', () => {
    const oversized = walk(ROOT)
      .map((file) => ({ file: relative(ROOT, file), bytes: statSync(file).size }))
      .filter((entry) => entry.bytes > MAX_BYTES)
      .sort((a, b) => b.bytes - a.bytes);
    expect(
      oversized,
      `files over ${MAX_BYTES / 1024}KB — split them (${oversized
        .map((o) => `${o.file}=${Math.round(o.bytes / 1024)}KB`)
        .join(', ')})`
    ).toEqual([]);
  });

  it('the walk is real (finds a known file)', () => {
    const files = walk(ROOT).map((f) => relative(ROOT, f).replace(/\\/g, '/'));
    expect(files.some((f) => f.endsWith('src/lib/api-guard.ts'))).toBe(true);
  });
});
