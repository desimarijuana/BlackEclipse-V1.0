import { afterEach, describe, expect, it, vi } from 'vitest';
import { generateChartSource, runNotebookCell } from './notebook-client';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('notebook client', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the cell source and chart inputs to the run route', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        status: 'ok',
        outputs: { total: 3 },
        artifacts: [{
          id: 'art_1',
          name: 'chart.png',
          bytes: 10,
          sha256: 'abc',
          mimeType: 'image/png',
          downloadUrl: '/artifacts/art_1/download',
        }],
        figure: null,
        provenance: { kind: 'computed', label: 'computed', detail: 'test' },
        durationMs: 12,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await runNotebookCell('chat_1', 'nb_1', 'result = 3', { chart: { kind: 'line' } });

    expect(result.status).toBe('ok');
    expect(result.outputs.total).toBe(3);
    expect(result.artifacts[0]?.downloadUrl).toBe('/api/artifacts/art_1/download');
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/harness/notebook/cells/nb_1/run');
    expect(JSON.parse(String(init.body))).toMatchObject({
      chatId: 'chat_1',
      source: 'result = 3',
      inputs: { chart: { kind: 'line' } },
    });
  });

  it('returns the generated chart source and unsupported marks', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      jsonResponse({ status: 'OK', source: 'print(1)', unsupported: ['violin'] }),
    ));
    const result = await generateChartSource({ kind: 'line' } as never);
    expect(result).toEqual({ source: 'print(1)', unsupported: ['violin'] });
  });

  it('returns a structured refusal so the cell can show it', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      jsonResponse({ status: 'refused', error: 'not allowed' }, 400),
    ));
    const result = await runNotebookCell('chat_1', 'nb_1', 'import os');
    expect(result.status).toBe('refused');
    expect(result.error).toBe('not allowed');
  });
});
