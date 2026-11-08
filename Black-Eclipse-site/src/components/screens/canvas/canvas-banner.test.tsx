import { afterEach, describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { useCommandStore } from '@/lib/search/store';
import type { CanvasContent } from '@/lib/canvas/content';
import { CanvasInlineNotice } from './canvas-banner';

function content(editable = false): CanvasContent {
  return {
    id: 'msg-1',
    kind: 'markdown',
    title: 'Eclipse response',
    markdown: '# Hello',
    editable,
    ...(editable ? { artifactId: 'art-1' } : {}),
  };
}

afterEach(() => {
  useCommandStore.getState().closeCanvas();
});

describe('Canvas store source', () => {
  it('records the message + title and keeps them when opening an artifact', () => {
    useCommandStore.getState().openCanvasContent(content(), { messageId: 'msg-1', title: 'Eclipse response' });
    expect(useCommandStore.getState().canvasSource).toEqual({ messageId: 'msg-1', title: 'Eclipse response' });

    useCommandStore.getState().openCanvas('art-1', { messageId: 'msg-1', title: 'Eclipse response' });
    expect(useCommandStore.getState().pendingCanvasArtifactId).toBe('art-1');
    expect(useCommandStore.getState().canvasSource?.messageId).toBe('msg-1');
  });

  it('closing the Canvas clears the source', () => {
    useCommandStore.getState().openCanvasContent(content(), { messageId: 'msg-1', title: 'Eclipse response' });
    useCommandStore.getState().closeCanvas();
    const state = useCommandStore.getState();
    expect(state.canvasView).toBeNull();
    expect(state.canvasSource).toBeNull();
    expect(state.canvasInlineOpen).toBe(false);
  });
});

describe('Canvas inline banner', () => {
  it('says the response is open in Canvas and can restore it', () => {
    const html = renderToStaticMarkup(
      <CanvasInlineNotice title="Eclipse response" canEdit onClose={() => {}} />,
    );
    expect(html).toContain('This response is open in');
    expect(html).toContain('Eclipse response');
    expect(html).toContain('Show in chat');
  });

  it('offers Edit for a snapshot but not for an already-editable surface', () => {
    const snapshot = renderToStaticMarkup(
      <CanvasInlineNotice title="Eclipse response" canEdit onClose={() => {}} />,
    );
    expect(snapshot).toContain('Edit');

    const editable = renderToStaticMarkup(
      <CanvasInlineNotice title="Eclipse response" canEdit={false} onClose={() => {}} />,
    );
    expect(editable).not.toContain('>Edit<');
  });
});
