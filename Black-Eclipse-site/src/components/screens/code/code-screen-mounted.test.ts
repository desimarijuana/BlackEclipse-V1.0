import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

// ── The Builder surface must be REACHABLE, not merely exported ───────────────
// `CodeScreen` was defined and exported but imported by nothing, so the Code
// screen, the land checks, the per-file diffs and the scorecard strip had no UI
// at all — and no test noticed, because a component that is never imported is
// never rendered and never fails. These assertions pin the wiring that makes it
// reachable: the shell mounts it, the tab union admits it, a deep link can boot
// it, and the palette can navigate to it. A later refactor that drops the mount
// fails here instead of silently shipping a dead screen.

function source(relative: string): string {
  return readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8');
}

describe('the Builder surface is mounted', () => {
  const shell = source('../stock-chat.tsx');
  const tabs = source('../../../lib/app-tabs.ts');
  const deepLink = source('../../../lib/search/deep-link.ts');
  const registry = source('../../../lib/search/registry.ts');

  it('the shell imports and renders the Builds wrapper', () => {
    expect(shell).toContain("import { CodeTab } from '@/components/screens/code/code-tab'");
    expect(shell).toContain('<CodeTab active={activeTab === \'code\'} />');
  });

  it('the wrapper loads CodeScreen', () => {
    const wrapper = source('./code-tab.tsx');
    expect(wrapper).toContain("import('./code-screen')");
    expect(wrapper).toContain('<CodeScreen />');
  });

  it('the shell gates it on the `code` tab', () => {
    expect(shell).toContain("visited.has('code')");
    expect(shell).toContain("activeTab === 'code'");
  });

  it('`code` is a real tab, deep-linkable, with a palette page', () => {
    // `APP_TABS` is a const tuple; `AppTab` is derived from it.
    expect(tabs).toContain("'code',");
    expect(deepLink).toContain('code: true');
    expect(registry).toContain("tab: 'code'");
  });

  it('the Builds surface names its project when it starts a build', () => {
    const screen = source('./code-screen.tsx');
    const list = source('./task-list.tsx');
    expect(screen).toContain('<ProjectBar onChange={setProjectRootId} />');
    expect(screen).toContain('workspaceRootId={projectRootId}');
    // Both create paths (a new draft and "Build this") name the project.
    expect(list).toContain('workspaceRootId?: string | null');
    expect(list.match(/\.\.\.project/g)?.length ?? 0).toBeGreaterThanOrEqual(2);
  });

  it('the Builds surface can run the project', () => {
    const screen = source('./code-screen.tsx');
    const panel = source('./preview-panel.tsx');
    expect(screen).toContain('<PreviewPanel taskId={selectedId} rootId={projectRootId} />');
    expect(panel).toContain('startCodePreview');
    expect(panel).toContain('stopCodePreview');
    expect(panel).toContain('getCodePreviewLogs');
  });

  it('the scorecard can be scoped to the selected project', () => {
    const screen = source('./code-screen.tsx');
    expect(screen).toContain("setScope('project')");
    expect(screen).toContain('getCodeScorecard(30, target)');
    expect(screen).toContain("scope === 'project' && projectRootId");
  });
});
