import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { DEFAULT_SIDEBAR_SECTIONS } from '@/lib/sidebar/config';
import { en } from '@/lib/i18n/dictionaries/en';

// Reachability guard: the Search Intelligence screen is a real, mounted surface,
// not dead code. It must import the client, be imported + rendered by the shell,
// be registered as an AppTab, and be listed in the sidebar with a plain-language
// label that names the capability (never a mechanism).

const siteRoot = path.resolve(fileURLToPath(new URL('.', import.meta.url)), '..', '..', '..', '..');

function read(rel: string): string {
  return readFileSync(path.join(siteRoot, rel), 'utf8');
}

const DENYLIST = ['pgvector', 'hnsw', 'embedding', 'vector space', 'reranker', 'bm25', 'fts5'];

describe('search screen reachability', () => {
  it('imports the front-door client', () => {
    const source = read('src/components/screens/search/search-screen.tsx');
    expect(source).toContain("@/lib/harness/search-client");
  });

  it('is imported and rendered by the shell', () => {
    const shell = read('src/components/screens/stock-chat.tsx');
    expect(shell).toContain('@/components/screens/search/search-screen');
    expect(shell).toContain('<SearchScreen />');
    expect(shell).toContain("visited.has('search')");
  });

  it('is a known tab and a sidebar section', () => {
    expect(read('src/lib/app-tabs.ts')).toContain("'search'");
    expect(DEFAULT_SIDEBAR_SECTIONS.some((s) => s.id === 'search')).toBe(true);
  });

  it('names the capability in plain language', () => {
    const label = en['nav.search'].toLowerCase();
    expect(label).toBeTruthy();
    const leaks = DENYLIST.filter((word) => label.includes(word));
    expect(leaks).toEqual([]);
  });
});
