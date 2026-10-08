import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { DEFAULT_SIDEBAR_SECTIONS } from '@/lib/sidebar/config';
import { navLabelKey } from '@/lib/i18n/nav';
import { en } from '@/lib/i18n/dictionaries/en';

// Reachability guard: the Tasks screen is a real, mounted surface fed by the
// durable Task / Plan store, not dead code and not mock data. It must import the
// browser client, be imported + rendered by the shell, be registered as an
// AppTab, be listed in the sidebar with a nav label key, and read real endpoints.

const siteRoot = path.resolve(fileURLToPath(new URL('.', import.meta.url)), '..', '..', '..', '..');

function read(rel: string): string {
  return readFileSync(path.join(siteRoot, rel), 'utf8');
}

describe('tasks screen reachability', () => {
  it('imports the browser front-door client (never the server client)', () => {
    const source = read('src/components/screens/tasks/tasks-screen.tsx');
    expect(source).toContain('@/lib/harness/tasks-browser');
    // The server client pulls child_process into the browser bundle — forbidden.
    expect(source).not.toContain('@/lib/harness/tasks-client');
  });

  it('reads real endpoints, not mock data', () => {
    const source = read('src/components/screens/tasks/tasks-screen.tsx');
    expect(source).toContain('listPlans');
    expect(source).toContain('getPlan');
    expect(source.toLowerCase()).not.toContain('mock');
  });

  it('is imported and rendered by the shell', () => {
    const shell = read('src/components/screens/stock-chat.tsx');
    expect(shell).toContain('@/components/screens/tasks/tasks-screen');
    expect(shell).toContain('<TasksScreen />');
    expect(shell).toContain("visited.has('tasks')");
  });

  it('is a known tab, a sidebar section and has a nav label key', () => {
    expect(read('src/lib/app-tabs.ts')).toContain("'tasks'");
    expect(DEFAULT_SIDEBAR_SECTIONS.some((s) => s.id === 'tasks')).toBe(true);
    expect(navLabelKey('tasks')).toBe('nav.tasks');
    expect(en['nav.tasks']).toBeTruthy();
  });
});
