// ── Eclipse Canvas tests ──────────────────────────────────────────────────────
//
// The vitest environment is `node` with no @testing-library/jsdom (see
// vitest.config.ts), so — like the response render tests — these render the real
// components with `react-dom/server` and assert on the markup. Data logic is
// verified through the pure error mapper. `CanvasScreen`'s empty state is
// renderable synchronously (no artifact selected), so it is asserted directly on
// the public component.

import { describe, expect, it, vi } from 'vitest';
import type { MutableRefObject } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import type { CanvasSnapshot } from '@/lib/harness/canvas-client';
import { CanvasScreen } from './canvas-screen';
import { CanvasWorkspace, type CanvasWorkspaceProps } from './canvas-workspace';
import type { CanvasAiPanelProps } from './canvas-ai-panel';
import type { CanvasRailProps } from './canvas-rail';
import type { CanvasCenterProps } from './canvas-center';
import {
  describeCanvasError, diffLines, monacoLanguage, contentExtension,
  type CanvasEditorHandle,
} from './canvas-utils';

vi.mock('@/lib/harness/canvas-client', () => ({
  listCanvasArtifacts: vi.fn(async () => []),
  createCanvasArtifact: vi.fn(),
  getCanvasArtifact: vi.fn(),
  saveCanvasArtifact: vi.fn(),
  restoreCanvasVersion: vi.fn(),
  proposeCanvasEdit: vi.fn(),
}));

vi.mock('@/lib/harness/artifacts-browser', () => ({
  updateArtifact: vi.fn(),
  archiveArtifact: vi.fn(),
}));

const noop = () => {};

function railProps(): CanvasRailProps {
  return {
    items: [], loading: false, error: null, query: '', onQueryChange: noop,
    onRefresh: noop, onSelect: noop, onCreate: noop, selectedId: null,
    collapsed: false, onToggleCollapsed: noop,
  };
}

function aiProps(): CanvasAiPanelProps {
  return {
    mode: 'ask', onModeChange: noop, instruction: '', onInstructionChange: noop,
    selection: null, useSelection: false, onToggleUseSelection: noop, onPropose: noop,
    proposing: false, proposal: null, onAccept: noop, onDiscard: noop, applying: false,
    error: null, conflictCurrentVersion: null, onReloadLatest: noop, currentContent: '',
    disabled: false, collapsed: false, onToggleCollapsed: noop,
  };
}

function centerProps(snapshot: CanvasSnapshot, content: string): CanvasCenterProps {
  const editorHandleRef = { current: null } as MutableRefObject<CanvasEditorHandle | null>;
  return {
    snapshot, content, dirty: false, saveState: 'idle', saveError: null,
    onContentChange: noop, onSelectionChange: noop, editorHandleRef,
    onRename: noop, onLanguageChange: noop, onRestore: noop, onExport: noop,
    onSaveNow: noop, onDelete: noop, fullWidth: false, onToggleFullWidth: noop, editable: true,
  };
}

function workspace(overrides: Partial<CanvasWorkspaceProps>): CanvasWorkspaceProps {
  return {
    rail: railProps(), center: null, ai: aiProps(),
    loadingArtifact: false, artifactError: null, onRetryArtifact: noop, onCreate: noop,
    ...overrides,
  };
}

const ENVELOPE = JSON.stringify({
  blocks: [{ type: 'markdown', markdown: 'CANVAS_LOADED_CONTENT' }],
});

const visualSnapshot: CanvasSnapshot = {
  artifactId: 'art-1', name: 'My Envelope', description: '', kind: 'visual',
  language: null, mimeType: 'application/json', content: ENVELOPE, version: 3,
  updatedAt: '2026-01-01T00:00:00.000Z', conversationId: null,
  versions: [{ versionNumber: 3, createdAt: '2026-01-01T00:00:00.000Z', changeNote: 'edited' }],
};

describe('CanvasScreen empty state', () => {
  it('renders the New actions when no artifact is selected', () => {
    const html = renderToStaticMarkup(<CanvasScreen isOperator={false} />);
    expect(html).toContain('New Document');
    expect(html).toContain('New Code');
    expect(html).toContain('New Visual Report');
  });
});

describe('CanvasWorkspace loaded artifact', () => {
  it('loads the artifact content into the editor and shows its name/kind', () => {
    const html = renderToStaticMarkup(
      <CanvasWorkspace
        {...workspace({
          center: centerProps(visualSnapshot, visualSnapshot.content),
          rail: { ...railProps(), items: [{
            artifactId: 'art-1', name: 'My Envelope', kind: 'visual', description: '',
            version: 3, updatedAt: '2026-01-01T00:00:00.000Z', language: null, conversationId: null,
          }], selectedId: 'art-1' },
        })}
      />,
    );
    expect(html).toContain('My Envelope');
    expect(html).toContain('Visual report');
    // The canonical content is present in the editor (the visual editor's source textarea).
    expect(html).toContain('CANVAS_LOADED_CONTENT');
  });

  it('previews a valid envelope through the response renderer', () => {
    const html = renderToStaticMarkup(
      <CanvasWorkspace {...workspace({ center: centerProps(visualSnapshot, visualSnapshot.content) })} />,
    );
    expect(html).toContain('CANVAS_LOADED_CONTENT');
    expect(html).not.toContain('invalid JSON');
  });
});

describe('CanvasWorkspace honest error state', () => {
  it('renders the real error message and never a fake success', () => {
    const error = describeCanvasError({ name: 'CanvasApiError', message: 'runtime unavailable', status: 503 });
    const html = renderToStaticMarkup(
      <CanvasWorkspace {...workspace({ artifactError: error, loadingArtifact: false })} />,
    );
    expect(html).toMatch(/unavailable/i);
    expect(html).toContain('Status 503');
    expect(html).not.toContain('Saved');
  });
});

describe('describeCanvasError maps client errors honestly', () => {
  it('maps a 503 CanvasApiError to a runtime-unavailable message', () => {
    const mapped = describeCanvasError({ name: 'CanvasApiError', message: 'boom', status: 503, code: 'RUNTIME_DOWN' });
    expect(mapped.status).toBe(503);
    expect(mapped.conflict).toBe(false);
    expect(mapped.message).toMatch(/unavailable/i);
  });

  it('maps a conflict error to the conflict state with the current version', () => {
    const mapped = describeCanvasError({ name: 'CanvasConflictError', message: 'changed', currentVersion: 7 });
    expect(mapped.conflict).toBe(true);
    expect(mapped.currentVersion).toBe(7);
  });
});

describe('canvas helpers', () => {
  it('maps language ids and file extensions for export', () => {
    expect(monacoLanguage('ts')).toBe('typescript');
    expect(monacoLanguage(null)).toBe('plaintext');
    expect(contentExtension('document', null)).toBe('md');
    expect(contentExtension('visual', null)).toBe('json');
    expect(contentExtension('code', 'python')).toBe('py');
  });

  it('produces a line diff for the review view', () => {
    const lines = diffLines('a\nb\nc', 'a\nB\nc');
    expect(lines.filter((l) => l.type === 'del').map((l) => l.text)).toContain('b');
    expect(lines.filter((l) => l.type === 'add').map((l) => l.text)).toContain('B');
  });
});
