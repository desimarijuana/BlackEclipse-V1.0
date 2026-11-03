'use client';

// ── Graph assistant panel ────────────────────────────────────────────────────
// Chat with an agent that edits THIS graph through validated operations. It
// never rewrites the document: the user sees exactly what will change and
// applies it as one undoable step. Nothing is auto-run.

import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Check, Loader2, Sparkles, Trash2, WarningCircle, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useGraphAssistant } from '@/lib/graph-studio/assistant-store';
import { describeOp } from '@/lib/graph-studio/assistant-ops';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';

const QUICK_PROMPTS: { text: string; mode: 'edit' | 'ask' }[] = [
  { text: 'Add a node that filters rows where volume is above 1M', mode: 'edit' },
  { text: 'Run it and fix any errors', mode: 'edit' },
  { text: 'Explain what this workflow does', mode: 'ask' },
  { text: 'Check the graph and tell me what is wrong', mode: 'edit' },
];

export function AssistantPanel({ onClose }: { onClose?: () => void }) {
  const messages = useGraphAssistant((s) => s.messages);
  const status = useGraphAssistant((s) => s.status);
  const pending = useGraphAssistant((s) => s.pending);
  const error = useGraphAssistant((s) => s.error);
  const progressLabel = useGraphAssistant((s) => s.progressLabel);
  const steps = useGraphAssistant((s) => s.steps);
  const autoApply = useGraphAssistant((s) => s.autoApply);
  const setAutoApply = useGraphAssistant((s) => s.setAutoApply);
  const send = useGraphAssistant((s) => s.send);
  const cancel = useGraphAssistant((s) => s.cancel);
  const applyPending = useGraphAssistant((s) => s.applyPending);
  const discardPending = useGraphAssistant((s) => s.discardPending);
  const reset = useGraphAssistant((s) => s.reset);
  const hydrate = useGraphAssistant((s) => s.hydrate);
  const workflowName = useGraphEditor((s) => s.ir?.name ?? 'workflow');
  const loadNonce = useGraphEditor((s) => s.loadNonce);
  const selectedCount = useGraphEditor((s) => s.selection.nodeIds.length);
  const run = useGraphEditor((s) => s.run);
  const failedRun = run?.status === 'failed'
    ? run.nodeRuns?.find((node) => node.status === 'failed') ?? null
    : null;

  const [text, setText] = useState('');
  const [mode, setMode] = useState<'edit' | 'ask'>('edit');
  const scrollerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, pending, status]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // A different workflow is a different conversation. `loadNonce` only bumps on
  // an explicit load, so auto-saving the assistant's own edits never swaps the
  // transcript. `hydrate` restores that workflow's saved thread.
  const lastNonce = useRef(loadNonce);
  useEffect(() => {
    hydrate(useGraphEditor.getState().workflowId);
    lastNonce.current = loadNonce;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (lastNonce.current === loadNonce) return;
    lastNonce.current = loadNonce;
    hydrate(useGraphEditor.getState().workflowId);
  }, [loadNonce, hydrate]);

  const submit = () => {
    const value = text.trim();
    if (!value || status === 'thinking') return;
    setText('');
    void send(value, mode);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-9 shrink-0 items-center justify-between border-b border-white/10 px-3">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          <Sparkles size={12} className="text-primary" /> Assistant
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={reset}
            title="New conversation"
            className="rounded p-1 text-muted-foreground hover:text-foreground"
          >
            <Trash2 size={12} />
          </button>
          {onClose && (
            <button type="button" onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground">
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      <div ref={scrollerRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {messages.length === 0 && (
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
            <p className="text-[12px] font-medium text-foreground">Build on this workflow</p>
            <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
              Ask for nodes, wiring or settings. Every change is validated against the node registry and
              shown before it touches <span className="text-foreground/80">{workflowName}</span>.
            </p>
            {failedRun && (
              <button
                type="button"
                onClick={() => {
                  setMode('edit');
                  const detail = failedRun.error ? `: ${failedRun.error}` : '';
                  void send(`The last run failed at ${failedRun.label}${detail}. Inspect the graph and fix it.`, 'edit');
                }}
                className="mt-2 flex w-full items-center gap-1.5 rounded-lg border border-rose-500/25 bg-rose-500/10 px-2 py-1.5 text-left text-[11px] text-rose-200 transition-colors hover:bg-rose-500/15"
              >
                <WarningCircle size={11} className="shrink-0" />
                <span className="min-w-0 flex-1 truncate">Fix the failed run{failedRun.label ? ` at ${failedRun.label}` : ''}</span>
              </button>
            )}
            <div className="mt-2 space-y-1">
              {QUICK_PROMPTS.map((prompt) => (
                <button
                  key={prompt.text}
                  type="button"
                  onClick={() => {
                    setMode(prompt.mode);
                    void send(prompt.text, prompt.mode);
                  }}
                  className="block w-full rounded-lg border border-white/10 bg-background/40 px-2 py-1.5 text-left text-[11px] text-muted-foreground transition-colors hover:border-primary/30 hover:text-foreground"
                >
                  {prompt.text}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message) => (
          <div key={message.id} className={cn('flex', message.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div
              className={cn(
                'max-w-[92%] whitespace-pre-wrap rounded-xl px-2.5 py-2 text-[12px] leading-relaxed',
                message.role === 'user'
                  ? 'bg-primary/15 text-foreground ring-1 ring-inset ring-primary/20'
                  : message.error
                    ? 'bg-rose-500/10 text-rose-200 ring-1 ring-inset ring-rose-500/20'
                    : 'bg-white/[0.04] text-foreground ring-1 ring-inset ring-white/10',
              )}
            >
              {message.content}
              {message.applied && (
                <span className="mt-1 flex items-center gap-1 text-[9.5px] font-medium text-emerald-300">
                  <Check size={9} /> Applied to the canvas — undo with Ctrl+Z
                </span>
              )}
              {message.runs && message.runs.length > 0 && (
                <span className="mt-1 flex flex-wrap gap-1">
                  {message.runs.map((run, index) => (
                    <span
                      key={`${run.run ?? index}-${run.status ?? 'run'}`}
                      title={run.failed?.[0]?.error ?? run.error ?? undefined}
                      className={cn(
                        'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] font-medium',
                        run.ok
                          ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                          : 'border-rose-500/30 bg-rose-500/10 text-rose-200',
                      )}
                    >
                      {run.ok ? <Check size={8} /> : <WarningCircle size={8} />}
                      Test run {run.run ?? index + 1}: {run.status ?? (run.ok ? 'succeeded' : 'failed')}
                      {!run.ok && run.failed?.[0]?.label ? ` · ${run.failed[0].label}` : ''}
                    </span>
                  ))}
                </span>
              )}
            </div>
          </div>
        ))}

        {status === 'thinking' && (
          <div className="rounded-xl border border-white/10 bg-white/[0.02] px-2.5 py-2">
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <Loader2 size={12} className="shrink-0 animate-spin" />
              <span className="min-w-0 flex-1 truncate">{progressLabel ?? 'Working on it…'}</span>
              <button
                type="button"
                onClick={cancel}
                className="shrink-0 rounded border border-white/10 px-1.5 py-0.5 text-[9.5px] text-muted-foreground hover:text-foreground"
              >
                Stop
              </button>
            </div>
            {steps.length > 0 && (
              <ul className="mt-1.5 space-y-0.5">
                {steps.map((step) => (
                  <li key={step.id} className="flex items-start gap-1.5 text-[10px] text-muted-foreground">
                    {step.state === 'running' ? (
                      <Loader2 size={9} className="mt-0.5 shrink-0 animate-spin text-primary" />
                    ) : step.state === 'ok' ? (
                      <Check size={9} className="mt-0.5 shrink-0 text-emerald-400" />
                    ) : (
                      <WarningCircle size={9} className="mt-0.5 shrink-0 text-amber-400" />
                    )}
                    <span className="min-w-0 flex-1 truncate">{step.label}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {pending && (
          <div className="rounded-xl border border-primary/25 bg-primary/[0.05] p-2.5">
            <p className="text-[11px] font-semibold text-foreground">Proposed change</p>
            <ul className="mt-1.5 space-y-1">
              {pending.ops.slice(0, 30).map((item, index) => (
                <li key={`${item.op}-${index}`} className="flex items-start gap-1.5 text-[10.5px] text-muted-foreground">
                  <Check size={10} className="mt-0.5 shrink-0 text-emerald-400" />
                  <span>{describeOp(item)}</span>
                </li>
              ))}
            </ul>
            {pending.warnings.length > 0 && (
              <ul className="mt-1.5 space-y-0.5">
                {pending.warnings.slice(0, 4).map((warning) => (
                  <li key={warning} className="flex items-start gap-1.5 text-[10px] text-amber-300">
                    <WarningCircle size={10} className="mt-0.5 shrink-0" />
                    <span>{warning}</span>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-2 flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => applyPending()}
                className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300 transition-colors hover:bg-emerald-500/15"
              >
                Apply {pending.ops.length} change{pending.ops.length === 1 ? '' : 's'}
              </button>
              <button
                type="button"
                onClick={discardPending}
                className="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
              >
                Discard
              </button>
              <span className="ml-auto text-[9.5px] text-muted-foreground/70">Applies as one undo step</span>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="flex shrink-0 items-start gap-1.5 border-t border-rose-500/20 bg-rose-500/10 px-3 py-1.5 text-[10.5px] text-rose-200">
          <span className="flex-1">{error}</span>
          {[...messages].reverse().find((message) => message.role === 'user') && (
            <button
              type="button"
              onClick={() => {
                const last = [...messages].reverse().find((message) => message.role === 'user');
                if (last) void send(last.content, mode);
              }}
              className="shrink-0 rounded border border-rose-400/30 px-1.5 py-0.5 text-[9.5px] hover:bg-rose-500/15"
            >
              Retry
            </button>
          )}
          <button type="button" onClick={() => useGraphAssistant.setState({ error: null })} className="shrink-0">
            <X size={11} />
          </button>
        </div>
      )}

      <div className="shrink-0 border-t border-white/10 p-2.5">
        <div className="mb-1.5 flex items-center gap-1">
          <button
            type="button"
            onClick={() => setMode('edit')}
            className={cn(
              'rounded px-1.5 py-0.5 text-[9.5px] font-medium uppercase tracking-wider transition-colors',
              mode === 'edit' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            Edit
          </button>
          <button
            type="button"
            onClick={() => setMode('ask')}
            className={cn(
              'rounded px-1.5 py-0.5 text-[9.5px] font-medium uppercase tracking-wider transition-colors',
              mode === 'ask' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            Ask
          </button>
          <button
            type="button"
            onClick={() => setAutoApply(!autoApply)}
            aria-pressed={autoApply}
            title={autoApply
              ? 'Safe edits apply to the canvas immediately; warnings/errors still need review'
              : 'Every edit waits for Apply/Discard'}
            className={cn(
              'ml-1 rounded border px-1.5 py-0.5 text-[9px] font-medium transition-colors',
              autoApply
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                : 'border-white/10 text-muted-foreground hover:text-foreground',
            )}
          >
            Auto-apply
          </button>
          <span className="ml-auto text-[9px] text-muted-foreground/70">
            {selectedCount > 0 ? `${selectedCount} selected · ` : ''}Enter to send
          </span>
        </div>
        <div className="flex items-end gap-1.5 rounded-lg border border-white/10 bg-background/60 px-2 py-1.5 focus-within:border-primary/40">
          <textarea
            ref={inputRef}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            placeholder={mode === 'edit' ? 'Describe the change…' : 'Ask about this workflow…'}
            className="max-h-32 min-h-[34px] flex-1 resize-none bg-transparent text-[12px] text-foreground outline-none placeholder:text-muted-foreground/60"
          />
          <button
            type="button"
            onClick={submit}
            disabled={!text.trim() || status === 'thinking'}
            title="Send"
            className={cn(
              'flex h-6 w-6 shrink-0 items-center justify-center rounded-md transition-colors',
              text.trim() && status !== 'thinking'
                ? 'bg-primary text-primary-foreground hover:opacity-90'
                : 'bg-white/5 text-muted-foreground',
            )}
          >
            <ArrowUp size={12} />
          </button>
        </div>
      </div>
    </div>
  );
}
