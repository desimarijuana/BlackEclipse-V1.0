import { describe, it, expect, vi, beforeEach } from 'vitest';

// Front-door contract for /api/theses. Creation is persisted + operator-gated,
// and input is validated before the store is ever touched.

const createThesis = vi.fn();
const listTheses = vi.fn();

vi.mock('@/lib/theses/store', () => ({
  createThesis: (...a: unknown[]) => createThesis(...a),
  listTheses: (...a: unknown[]) => listTheses(...a),
}));

import { GET, POST } from '@/app/api/theses/route';

function req(body: unknown, origin = 'http://localhost:3000'): Request {
  return new Request('http://localhost:3000/api/theses', {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  });
}

describe('GET /api/theses', () => {
  it('lists theses', async () => {
    listTheses.mockResolvedValueOnce([{ id: 'a', symbol: 'AAPL' }]);
    const res = await GET(new Request('http://localhost:3000/api/theses'));
    expect(res.status).toBe(200);
    expect((await res.json()).theses).toEqual([{ id: 'a', symbol: 'AAPL' }]);
  });
});

describe('POST /api/theses', () => {
  beforeEach(() => createThesis.mockReset());

  it('refuses a cross-origin create before writing', async () => {
    const res = await POST(req({ symbol: 'AAPL' }, 'http://evil.example'));
    expect(res.status).toBe(403);
    expect(createThesis).not.toHaveBeenCalled();
  });

  it('rejects a missing required field', async () => {
    const res = await POST(req({ symbol: 'AAPL', marketId: 'US' }));
    expect(res.status).toBe(400);
    expect(createThesis).not.toHaveBeenCalled();
  });

  it('rejects an invalid status', async () => {
    const res = await POST(req({
      symbol: 'AAPL', marketId: 'US', title: 't', hypothesis: 'h', status: 'moon',
    }));
    expect(res.status).toBe(400);
    expect(createThesis).not.toHaveBeenCalled();
  });

  it('creates a thesis for an operator', async () => {
    createThesis.mockResolvedValueOnce({ id: 'th1', symbol: 'AAPL', version: 1 });
    const res = await POST(req({
      symbol: 'AAPL', marketId: 'US', title: 'Long-term compounder', hypothesis: 'Services growth',
      assumptions: ['margin expansion'],
    }));
    expect(res.status).toBe(201);
    expect((await res.json()).thesis.id).toBe('th1');
    expect(createThesis).toHaveBeenCalledWith(expect.objectContaining({
      symbol: 'AAPL', marketId: 'US', assumptions: ['margin expansion'],
    }));
  });
});
