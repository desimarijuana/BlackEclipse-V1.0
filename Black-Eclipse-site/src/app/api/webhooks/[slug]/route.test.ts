// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { signWebhook } from '@/lib/graph-studio/webhook-crypto';

const store = vi.hoisted(() => ({
  getWebhookForDelivery: vi.fn(),
  readWebhookSecret: vi.fn(),
  verifyArmed: vi.fn(),
  claimDelivery: vi.fn(),
  setDeliveryRun: vi.fn(),
  recordDelivery: vi.fn(),
}));

const runServer = vi.hoisted(() => ({ startPersistedRun: vi.fn() }));

vi.mock('@/lib/graph-studio/webhook-store', () => store);
vi.mock('@/lib/graph-studio/run-server', () => runServer);
vi.mock('@/lib/harness/python-runtime', () => ({ HARNESS_PY_URL: 'http://python.test' }));
vi.mock('@/lib/harness/runtime-auth', () => ({ runtimeCallbackToken: () => '' }));
vi.mock('@/lib/api-guard', () => ({
  clientKey: () => '127.0.0.1',
  rateLimit: () => ({ ok: true, remaining: 10, retryAfterSec: 0 }),
}));

import { POST } from './route';

const SECRET = 'test-secret';

function record(overrides: Record<string, unknown> = {}) {
  return {
    id: 'wh_1',
    workflowId: 'wf_1',
    nodeId: 'hook',
    name: 'Hook',
    slug: 's1',
    endpoint: '/api/webhooks/s1',
    enabled: true,
    mode: 'safe',
    allowedMethods: ['POST'],
    responseMode: 'immediate',
    responseTimeoutMs: 10_000,
    verificationMode: 'hmac',
    version: null,
    grantsJson: null,
    secretHint: 'cret',
    lastReceivedAt: null,
    lastRunId: null,
    lastStatus: null,
    lastError: null,
    createdAt: '2026-11-01T00:00:00.000Z',
    updatedAt: '2026-11-01T00:00:00.000Z',
    ...overrides,
  };
}

function signedRequest(body: string, overrides: Record<string, string> = {}) {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const headers = new Headers({
    'content-type': 'application/json',
    'x-eclipse-timestamp': timestamp,
    'x-eclipse-signature': signWebhook(SECRET, timestamp, body),
    ...overrides,
  });
  return new Request('http://localhost/api/webhooks/s1', { method: 'POST', headers, body });
}

const ctx = { params: Promise.resolve({ slug: 's1' }) };

beforeEach(() => {
  vi.clearAllMocks();
  store.getWebhookForDelivery.mockResolvedValue({
    record: record(),
    row: { secretCipher: 'cipher' },
  });
  store.readWebhookSecret.mockReturnValue(SECRET);
  store.verifyArmed.mockResolvedValue({ ok: true, version: null });
  store.claimDelivery.mockResolvedValue({ duplicate: false });
  store.setDeliveryRun.mockResolvedValue(undefined);
  store.recordDelivery.mockResolvedValue(undefined);
  runServer.startPersistedRun.mockResolvedValue({
    ok: true,
    status: 201,
    run: { id: 'run_1' },
  });
});

describe('public workflow webhook', () => {
  it('starts a safe run from a valid signature', async () => {
    const body = JSON.stringify({ hello: 'world' });
    const res = await POST(signedRequest(body), ctx);
    expect(res.status).toBe(202);
    const data = await res.json();
    expect(data).toEqual({ accepted: true, runId: 'run_1' });
    const call = runServer.startPersistedRun.mock.calls[0][0];
    expect(call).toMatchObject({ workflowId: 'wf_1', runInput: { hello: 'world' } });
    expect(call.authorization).toBeUndefined();
    expect(call.version).toBeUndefined();
    expect(call.triggerContext).toMatchObject({ method: 'POST', signatureVerified: true });
    expect(store.recordDelivery).toHaveBeenCalledWith('wh_1', expect.objectContaining({ runId: 'run_1' }));
  });

  it('rejects a tampered body without starting a run', async () => {
    const request = signedRequest('{"hello":"world"}');
    const tampered = new Request(request.url, {
      method: 'POST',
      headers: request.headers,
      body: '{"hello":"attacker"}',
    });
    const res = await POST(tampered, ctx);
    expect(res.status).toBe(401);
    expect(runServer.startPersistedRun).not.toHaveBeenCalled();
  });

  it('returns 404 for an unknown or disabled endpoint', async () => {
    store.getWebhookForDelivery.mockResolvedValueOnce({ record: record({ enabled: false }), row: {} });
    expect((await POST(signedRequest('{}'), ctx)).status).toBe(404);

    store.getWebhookForDelivery.mockResolvedValueOnce(null);
    expect((await POST(signedRequest('{}'), ctx)).status).toBe(404);
  });

  it('enforces the method filter', async () => {
    store.getWebhookForDelivery.mockResolvedValueOnce({
      record: record({ allowedMethods: ['GET'] }),
      row: {},
    });
    expect((await POST(signedRequest('{}'), ctx)).status).toBe(405);
  });

  it('runs an armed delivery against the pinned version and grant', async () => {
    store.getWebhookForDelivery.mockResolvedValueOnce({
      record: record({ mode: 'armed', version: 3, grantsJson: '{"allowNetwork":true}' }),
      row: {},
    });
    store.verifyArmed.mockResolvedValueOnce({
      ok: true,
      version: 3,
      authorization: { operator: true, allowNetwork: true },
    });
    const res = await POST(signedRequest('{}'), ctx);
    expect(res.status).toBe(202);
    const call = runServer.startPersistedRun.mock.calls[0][0];
    expect(call.version).toBe(3);
    expect(call.authorization).toEqual({ operator: true, allowNetwork: true });
  });

  it('refuses when the arm is invalid', async () => {
    store.getWebhookForDelivery.mockResolvedValueOnce({ record: record({ mode: 'armed' }), row: {} });
    store.verifyArmed.mockResolvedValueOnce({ ok: false, error: 'the graph changed' });
    const res = await POST(signedRequest('{}'), ctx);
    expect(res.status).toBe(409);
    expect(runServer.startPersistedRun).not.toHaveBeenCalled();
  });

  it('dedupes an explicit delivery id', async () => {
    store.claimDelivery.mockResolvedValueOnce({ duplicate: true, runId: 'run_prev' });
    const res = await POST(signedRequest('{}', { 'x-eclipse-delivery': 'evt_1' }), ctx);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ duplicate: true, runId: 'run_prev', accepted: true });
    expect(runServer.startPersistedRun).not.toHaveBeenCalled();
  });

  it('rejects a payload larger than the run-input cap', async () => {
    const res = await POST(signedRequest('x'.repeat(70_000)), ctx);
    expect(res.status).toBe(413);
    expect(runServer.startPersistedRun).not.toHaveBeenCalled();
  });

  it('accepts a token proof when configured', async () => {
    store.getWebhookForDelivery.mockResolvedValueOnce({
      record: record({ verificationMode: 'token' }),
      row: {},
    });
    const timestamp = String(Math.floor(Date.now() / 1000));
    const request = new Request('http://localhost/api/webhooks/s1', {
      method: 'POST',
      headers: { 'x-eclipse-token': SECRET, 'x-eclipse-timestamp': timestamp },
      body: '{}',
    });
    expect((await POST(request, ctx)).status).toBe(202);
  });
});
