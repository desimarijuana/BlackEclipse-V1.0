import { afterEach, describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { useCommandStore } from '@/lib/search/store';
import type { CanvasContent } from '@/lib/canvas/content';
import { CanvasInlineNotice, CanvasPageBanner } from './canvas-banner';

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

describe('Canvas page banner', () => {
  it('names the open source and offers Edit + Show in chat for a snapshot', () => {
    const html = renderToStaticMarkup(
      <CanvasPageBanner title="Eclipse response" canEdit onClose={() => {}} />,
    );
    expect(html).toContain('Canvas');
    expect(html).toContain('Eclipse response');
    expect(html).toContain('Edit');
    expect(html).toContain('Show in chat');
  });

  it('drops Edit once the surface is already editable', () => {
    const html = renderToStaticMarkup(
      <CanvasPageBanner title="Eclipse response" canEdit={false} onClose={() => {}} />,
    );
    expect(html).not.toContain('>Edit<');
    expect(html).toContain('Show in chat');
  });
});

describe('Canvas inline notice', () => {
  it('says the response is open in Canvas and can restore it', () => {
    const html = renderToStaticMarkup(
      <CanvasInlineNotice title="Eclipse response" canEdit onClose={() => {}} />,
    );
    expect(html).toContain('This response is open in');
    expect(html).toContain('Eclipse response');
    expect(html).toContain('Show in chat');
  });
});
