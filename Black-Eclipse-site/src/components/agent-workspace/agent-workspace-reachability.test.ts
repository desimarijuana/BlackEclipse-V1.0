import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { en } from '@/lib/i18n/dictionaries/en';

// The Agent Workspace is a real docked RIGHT SIDEBAR, mounted in the app shell
// (`stock-chat.tsx`) as a sibling column of the main panel — so the main panel
// shrinks rather than being overlapped. Like the code surface, its reachability
// is not observable from a unit test that imports the panel directly, so this
// asserts on the SHELL SOURCES: if someone removes the shell mount or the
// top-bar toggle, the sidebar goes dark and this fails.

function readShell(): string {
  const here = fileURLToPath(new URL('../screens/stock-chat.tsx', import.meta.url));
  return readFileSync(here, 'utf8');
}
function readTopBar(): string {
  const here = fileURLToPath(new URL('../layout/top-bar.tsx', import.meta.url));
  return readFileSync(here, 'utf8');
}

describe('Agent Workspace reachability', () => {
  it('is mounted once in the app shell row', () => {
    const shell = readShell();
    expect(shell).toContain('components/agent-workspace/workspace');
    expect(shell).toContain('<AgentWorkspace');
  });

  it('has a header toggle so it is reachable from every screen', () => {
    expect(readTopBar()).toContain('AgentWorkspaceToggle');
  });

  it('feeds from the ONE existing chat stream (no second bus)', () => {
    const here = fileURLToPath(new URL('../../lib/agent/registry.ts', import.meta.url));
    const registry = readFileSync(here, 'utf8');
    expect(registry).toContain('ingestHarnessFrame');
  });

  it('scrolls the panel body so stacked context data is never clipped', () => {
    const here = fileURLToPath(new URL('./workspace.tsx', import.meta.url));
    const src = readFileSync(here, 'utf8');
    expect(src).toContain('overflow-y-auto');
  });
});

describe('Agent Workspace copy', () => {
  const KEYS = [
    'workspace.title',
    'workspace.empty',
    'workspace.panel.output',
    'workspace.panel.changes',
    'workspace.panel.permissions',
    'workspace.panel.history',
    'workspace.permission.approve',
    'workspace.permission.deny',
    'workspace.notAvailable',
  ] as const;

  it('declares every core label', () => {
    for (const key of KEYS) expect(en[key], key).toBeTruthy();
  });

  it('never names a mechanism in the user-facing labels', () => {
    const denylist = ['chain-of-thought', 'sandbox', 'worktree', 'argv', 'stderr'];
    for (const key of KEYS) {
      const text = (en[key] ?? '').toLowerCase();
      for (const word of denylist) expect(text, `${key} leaks ${word}`).not.toContain(word);
    }
  });
});
