'use client';

// ── Webhook panel ────────────────────────────────────────────────────────────
// The trigger.webhook node's real controls. The node is zero-config; the
// endpoint, secret, method filter, response mode and armed grants live on a
// WorkflowWebhook linked by `nodeId`, so the graph and the endpoint cannot drift.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Copy, Globe, Play, RefreshCw, Square, Trash2 } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { copyText } from '@/lib/desktop/clipboard';
import {
  createWebhook,
  deleteWebhook,
  listWebhooks,
  rotateWebhookSecret,
  updateWebhook,
  WebhookApiError,
  type WebhookResponseMode,
  type WebhookVerificationMode,
  type WorkflowWebhook,
} from '@/lib/graph-studio/webhook-client';

const METHODS = ['POST', 'GET', 'PUT', 'PATCH', 'DELETE'];

function formatWhen(iso: string | null): string {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
}

export function WebhookPanel({
  workflowId,
  nodeId,
}: {
  workflowId: string | null;
  nodeId: string;
}) {
  const [webhooks, setWebhooks] = useState<WorkflowWebhook[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);

  const [name, setName] = useState('Webhook');
  const [methods, setMethods] = useState<string[]>(['POST']);
  const [verificationMode, setVerificationMode] = useState<WebhookVerificationMode>('hmac');
  const [responseMode, setResponseMode] = useState<WebhookResponseMode>('immediate');
  const [timeoutMs, setTimeoutMs] = useState(10_000);
  const [allowNetwork, setAllowNetwork] = useState(false);

  const webhook = useMemo(() => {
    const linked = webhooks.find((item) => item.nodeId === nodeId);
    if (linked) return linked;
    const unlinked = webhooks.filter((item) => !item.nodeId);
    return unlinked.length === 1 ? unlinked[0] : null;
  }, [webhooks, nodeId]);

  const refresh = useCallback(async () => {
    if (!workflowId) {
      setWebhooks([]);
      return;
    }
    setLoading(true);
    try {
      setWebhooks(await listWebhooks(workflowId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load webhooks');
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!webhook) return;
    setName(webhook.name);
    setMethods(webhook.allowedMethods);
    setVerificationMode(webhook.verificationMode);
    setResponseMode(webhook.responseMode);
    setTimeoutMs(webhook.responseTimeoutMs);
    setAllowNetwork(webhook.mode === 'armed');
  }, [webhook?.id, webhook?.updatedAt]); // eslint-disable-line react-hooks/exhaustive-deps

  const endpoint = webhook?.endpoint ?? '';
  const copyEndpoint = () => {
    if (!webhook) return;
    const base = typeof window === 'undefined' ? '' : window.location.origin;
    return copy(`${base}${webhook.endpoint}`);
  };

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (err) {
      setError(err instanceof WebhookApiError ? err.message : err instanceof Error ? err.message : 'Request failed');
    } finally {
      setBusy(false);
    }
  };

  const create = () => run(async () => {
    const created = await createWebhook(workflowId as string, { nodeId, name: name.trim() || 'Webhook' });
    setSecret(created.secret);
  });

  const save = () => {
    if (!webhook) return;
    return run(() => updateWebhook(webhook.id, {
      // Adopt a legacy unlinked webhook into this node on first save.
      nodeId: webhook.nodeId ? undefined : nodeId,
      name: name.trim() || 'Webhook',
      allowedMethods: methods,
      verificationMode,
      responseMode,
      responseTimeoutMs: timeoutMs,
    }));
  };

  const copy = async (value: string) => {
    if (!(await copyText(value))) {
      setError('Clipboard is unavailable — select and copy the value manually.');
    }
  };

  if (!workflowId) {
    return (
      <p className="px-3 py-3 text-[11px] text-muted-foreground">
        Save this workflow first — a webhook starts a run of the persisted version.
      </p>
    );
  }

  return (
    <div className="space-y-3 px-3 py-3">
      <div className="rounded-md border border-white/10 bg-white/[0.02] p-2">
        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          <Globe size={11} /> Inbound webhook
        </div>
        <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
          The caller proves authenticity with an HMAC signature (or a token). Safe mode runs the
          read-only test envelope. Arm it to run a pinned version with the network grant you confirm.
        </p>
      </div>

      {error && <p className="rounded bg-rose-500/10 px-2 py-1 text-[10px] text-rose-200">{error}</p>}

      {secret && (
        <div className="rounded-md border border-emerald-400/30 bg-emerald-500/10 p-2">
          <div className="text-[10px] font-medium text-emerald-100">Copy this secret now — it is shown once</div>
          <div className="mt-1 flex items-center gap-1">
            <code className="min-w-0 flex-1 break-all rounded bg-black/30 px-1.5 py-1 font-mono text-[9.5px] text-emerald-50">
              {secret}
            </code>
            <button
              type="button"
              onClick={() => void copy(secret)}
              title="Copy secret"
              className="rounded border border-emerald-400/30 p-1 text-emerald-100 hover:bg-emerald-500/20"
            >
              <Copy size={11} />
            </button>
          </div>
          <button
            type="button"
            onClick={() => setSecret(null)}
            className="mt-1 text-[9.5px] text-emerald-200 underline-offset-2 hover:underline"
          >
            I saved it
          </button>
        </div>
      )}

      {webhook ? (
        <>
          <div className="rounded-md border border-white/10 bg-white/[0.02] px-2 py-1.5">
            <div className="flex items-center gap-1.5">
              <span className={cn('h-1.5 w-1.5 rounded-full', webhook.enabled ? 'bg-emerald-400' : 'bg-slate-600')} />
              <span className="text-[10.5px] text-foreground">
                {webhook.enabled ? 'Active' : 'Paused'} · {webhook.mode === 'armed' ? `armed v${webhook.version ?? '?'}` : 'safe'}
              </span>
              <span className="ml-auto text-[9.5px] text-muted-foreground">
                {webhook.lastStatus ? `last ${webhook.lastStatus}` : 'never received'}
              </span>
            </div>
            <div className="mt-0.5 text-[9.5px] text-muted-foreground">
              last delivery {formatWhen(webhook.lastReceivedAt)}
              {webhook.lastRunId ? ` · run ${webhook.lastRunId}` : ''}
            </div>
            {webhook.lastError && <div className="text-[9.5px] text-rose-300">{webhook.lastError}</div>}
            <div className="mt-1 flex items-center gap-1">
              <code className="min-w-0 flex-1 truncate rounded bg-black/25 px-1.5 py-1 font-mono text-[9.5px] text-muted-foreground">
                {endpoint}
              </code>
              <button
                type="button"
                onClick={() => void copyEndpoint()}
                title="Copy webhook URL"
                className="rounded border border-white/10 p-1 text-muted-foreground hover:text-foreground"
              >
                <Copy size={11} />
              </button>
            </div>
            <div className="mt-1 text-[9px] text-muted-foreground/80">secret ····{webhook.secretHint}</div>
          </div>

          <label className="block">
            <span className="mb-0.5 block text-[10px] text-muted-foreground">Name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
            />
          </label>

          <div>
            <span className="mb-1 block text-[10px] text-muted-foreground">Accepted methods</span>
            <div className="flex flex-wrap gap-1">
              {METHODS.map((method) => {
                const on = methods.includes(method);
                return (
                  <button
                    key={method}
                    type="button"
                    onClick={() => setMethods(on ? methods.filter((item) => item !== method) : [...methods, method])}
                    className={cn(
                      'rounded-md border px-1.5 py-0.5 text-[10px]',
                      on
                        ? 'border-primary/40 bg-primary/15 text-foreground'
                        : 'border-white/10 text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {method}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-0.5 block text-[10px] text-muted-foreground">Proof</span>
              <select
                value={verificationMode}
                onChange={(event) => setVerificationMode(event.target.value as WebhookVerificationMode)}
                className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
              >
                <option value="hmac">HMAC signature</option>
                <option value="token">Token header</option>
                <option value="both">Either</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-0.5 block text-[10px] text-muted-foreground">Response</span>
              <select
                value={responseMode}
                onChange={(event) => setResponseMode(event.target.value as WebhookResponseMode)}
                className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
              >
                <option value="immediate">202 + run id</option>
                <option value="wait">Wait for result</option>
              </select>
            </label>
          </div>

          {responseMode === 'wait' && (
            <label className="block">
              <span className="mb-0.5 block text-[10px] text-muted-foreground">Wait limit (ms)</span>
              <input
                type="number"
                min={1_000}
                max={30_000}
                step={500}
                value={timeoutMs}
                onChange={(event) => setTimeoutMs(Number(event.target.value) || 10_000)}
                className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/50"
              />
            </label>
          )}

          <label className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <input
              type="checkbox"
              checked={allowNetwork}
              onChange={(event) => setAllowNetwork(event.target.checked)}
            />
            Allow network when arming (only if this graph needs it)
          </label>

          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => void save()}
              disabled={busy || loading}
              className="graph-accent rounded-md border px-2.5 py-1 text-[10.5px] disabled:opacity-40"
            >
              Save webhook
            </button>
            {webhook.mode === 'armed' ? (
              <button
                type="button"
                onClick={() => void run(() => updateWebhook(webhook.id, { mode: 'safe' }))}
                disabled={busy}
                className="rounded-md border border-white/10 px-2 py-1 text-[10.5px] text-muted-foreground hover:text-foreground disabled:opacity-40"
              >
                Return to safe
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void run(() => updateWebhook(webhook.id, { mode: 'armed', allowNetwork }))}
                disabled={busy}
                className="flex items-center gap-1 rounded-md border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[10.5px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-40"
              >
                <Play size={10} /> Arm webhook
              </button>
            )}
            <button
              type="button"
              onClick={() => void run(() => updateWebhook(webhook.id, { enabled: !webhook.enabled }))}
              disabled={busy}
              className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[10.5px] text-muted-foreground hover:text-foreground disabled:opacity-40"
            >
              <Square size={10} /> {webhook.enabled ? 'Pause' : 'Resume'}
            </button>
            <button
              type="button"
              onClick={() => void run(async () => {
                const rotated = await rotateWebhookSecret(webhook.id);
                setSecret(rotated.secret);
              })}
              disabled={busy}
              title="Rotate secret"
              className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[10.5px] text-muted-foreground hover:text-foreground disabled:opacity-40"
            >
              <RefreshCw size={10} /> Rotate
            </button>
            <button
              type="button"
              onClick={() => void run(() => deleteWebhook(webhook.id))}
              disabled={busy}
              title="Delete webhook"
              className="ml-auto rounded-md border border-rose-500/25 p-1 text-rose-300 hover:bg-rose-500/10 disabled:opacity-40"
            >
              <Trash2 size={11} />
            </button>
          </div>

          <p className="text-[9.5px] leading-relaxed text-muted-foreground/80">
            {webhook.mode === 'armed'
              ? 'Armed runs stay on the pinned version and grant above. A later save does not move the pin; re-arm to use a newer version.'
              : 'Safe mode can read and compute but cannot use the network, write files or trade. Arm the webhook for network integrations.'}
          </p>
        </>
      ) : (
        <button
          type="button"
          onClick={() => void create()}
          disabled={busy || loading}
          className="graph-accent w-full rounded-md border px-2.5 py-1.5 text-[11px] disabled:opacity-40"
        >
          Create webhook endpoint
        </button>
      )}
    </div>
  );
}
