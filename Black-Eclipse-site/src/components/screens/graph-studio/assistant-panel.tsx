'use client';

// ── Graph assistant panel ────────────────────────────────────────────────────
// Chat with an agent that edits THIS graph through validated operations. It
// never rewrites the document: the user sees exactly what will change and
// applies it as one undoable step. Nothing is auto-run.
//
// The turn is a real run: Pause/Resume/Stop route to /api/graphs/assist/runs/…
// and the panel exposes the same controls a normal chat page does. A proposal
// that needs review is an approval, not a silent apply.

import { useEffect, useRef, useState } from 'react';
import {
  ArrowUp, Check, History, Loader2, Pause, Play, Plus, Sparkles, Square, WarningCircle, X,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useGraphAssistant } from '@/lib/graph-studio/assistant-store';
import { describeOp } from '@/lib/graph-studio/assistant-ops';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { AssistantContent } from '@/components/chat/assistant-content';
import { CopyButton } from '@/components/chat/copy-button';
import { ModelSelector } from '@/components/chat/chat-input';
import { useChatModel } from '@/lib/agent/use-chat-model';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

const QUICK_PROMPTS: { text: string; mode: 'edit' | 'ask' }[] = [
  { text: 'Add a node that filters rows where volume is above 1M', mode: 'edit' },
  { text: 'Run it and fix any errors', mode: 'edit' },
  { text: 'Explain what this workflow does', mode: 'ask' },
  { text: 'Check the graph and tell me what is wrong', mode: 'edit' },
];

export function AssistantPanel({ onClose }: { onClose?: () => void }) {
  const messages = useGraphAssistant((s) => s.messages);
  const status = useGraphAssistant((s) => s.status);
  const runId = useGraphAssistant((s) => s.runId);
  const pending = useGraphAssistant((s) => s.pending);
  const toolApproval = useGraphAssistant((s) => s.toolApproval);
  const error = useGraphAssistant((s) => s.error);
  const progressLabel = useGraphAssistant((s) => s.progressLabel);
  const steps = useGraphAssistant((s) => s.steps);
  const autoApply = useGraphAssistant((s) => s.autoApply);
  const setAutoApply = useGraphAssistant((s) => s.setAutoApply);
  const send = useGraphAssistant((s) => s.send);
  const pause = useGraphAssistant((s) => s.pause);
  const resume = useGraphAssistant((s) => s.resume);
  const cancel = useGraphAssistant((s) => s.cancel);
  const applyPending = useGraphAssistant((s) => s.applyPending);
  const decidePending = useGraphAssistant((s) => s.decidePending);
  const decideToolApproval = useGraphAssistant((s) => s.decideToolApproval);
  const answerClarification = useGraphAssistant((s) => s.answerClarification);
  const discardPending = useGraphAssistant((s) => s.discardPending);
  const hydrate = useGraphAssistant((s) => s.hydrate);
  const threads = useGraphAssistant((s) => s.threads);
  const activeThreadId = useGraphAssistant((s) => s.activeThreadId);
  const newThread = useGraphAssistant((s) => s.newThread);
  const selectThread = useGraphAssistant((s) => s.selectThread);
  const workflowName = useGraphEditor((s) => s.ir?.name ?? 'workflow');
  const loadNonce = useGraphEditor((s) => s.loadNonce);
  const selectedCount = useGraphEditor((s) => s.selection.nodeIds.length);
  const run = useGraphEditor((s) => s.run);
  const failedRun = run?.status === 'failed'
    ? run.nodeRuns?.find((node) => node.status === 'failed') ?? null
    : null;

  const [text, setText] = useState('');
  const [mode, setMode] = useState<'edit' | 'ask'>('edit');
  const [answer, setAnswer] = useState('');
  const chatModel = useChatModel();
  const modelChoice = { provider: chatModel.selectedProvider, model: chatModel.displayModel };
  const scrollerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const busy = status !== 'idle';
  const approval = pending?.approval ?? null;
  const approvalBlocked = approval?.status === 'denied' || approval?.status === 'expired';
  const clarification = pending?.clarification ?? null;
  const proposal = pending && pending.ops.length > 0 ? pending : null;

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
    if (!value || busy) return;
    setText('');
    void send(value, mode, modelChoice);
  };

  const regenerate = (assistantId: string) => {
    const index = messages.findIndex((message) => message.id === assistantId);
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      if (messages[cursor].role === 'user') {
        void send(messages[cursor].content, mode, modelChoice);
        return;
      }
    }
  };

  const submitAnswer = () => {
    const value = answer.trim();
    if (!value || busy) return;
    setAnswer('');
    void answerClarification(value);
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
          {busy && (
            <span
              className={cn(
                'ml-1 rounded border px-1 py-0.5 text-[8.5px] font-medium normal-case tracking-normal',
                status === 'paused'
                  ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                  : status === 'awaiting_approval'
                    ? 'border-primary/30 bg-primary/10 text-primary'
                    : 'border-sky-500/30 bg-sky-500/10 text-sky-300',
              )}
            >
              {status === 'paused' ? 'paused' : status === 'awaiting_approval' ? 'approval' : 'running'}
            </span>
          )}
        </span>
        <div className="flex items-center gap-1">
          {status === 'running' && (
            <button
              type="button"
              onClick={() => void pause()}
              title="Pause after the current step"
              className="rounded p-1 text-muted-foreground hover:text-foreground"
            >
              <Pause size={12} />
            </button>
          )}
          {status === 'paused' && (
            <button
              type="button"
              onClick={() => void resume()}
              title="Resume"
              className="rounded p-1 text-emerald-300 hover:text-emerald-200"
            >
              <Play size={12} />
            </button>
          )}
          {busy && (
            <button
              type="button"
              onClick={cancel}
              title="Stop"
              className="rounded p-1 text-rose-300 hover:text-rose-200"
            >
              <Square size={10} />
            </button>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <button
                  type="button"
                  title="Conversation history"
                  className="rounded p-1 text-muted-foreground hover:text-foreground"
                />
              }
            >
              <History size={12} />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuLabel>Conversations</DropdownMenuLabel>
              <DropdownMenuItem onClick={newThread}>
                <Plus size={11} /> New conversation
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {threads.filter((thread) => thread.messages.length > 0).slice(0, 12).map((thread) => (
                <DropdownMenuItem
                  key={thread.id}
                  onClick={() => selectThread(thread.id)}
                  className={cn('flex-col items-start gap-0.5', thread.id === activeThreadId && 'bg-primary/10')}
                >
                  <span className="w-full truncate text-[11px]">{thread.title}</span>
                  <span className="text-[9px] text-muted-foreground">
                    {new Date(thread.updatedAt).toLocaleDateString()}
                  </span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <button
            type="button"
            onClick={newThread}
            title="New conversation"
            className="rounded p-1 text-muted-foreground hover:text-foreground"
          >
            <Plus size={12} />
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
                  void send(`The last run failed at ${failedRun.label}${detail}. Inspect the graph and fix it.`, 'edit', modelChoice);
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
                    void send(prompt.text, prompt.mode, modelChoice);
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
                'max-w-full rounded-xl px-2.5 py-2 text-[12px] leading-relaxed',
                message.role === 'user'
                  ? 'max-w-[92%] whitespace-pre-wrap bg-primary/15 text-foreground ring-1 ring-inset ring-primary/20'
                  : message.error
                    ? 'whitespace-pre-wrap bg-rose-500/10 text-rose-200 ring-1 ring-inset ring-rose-500/20'
                    : 'bg-white/[0.04] text-foreground ring-1 ring-inset ring-white/10',
              )}
            >
              {message.role === 'assistant' && !message.error ? (
                <AssistantContent
                  content={message.content}
                  compact
                  streaming={Boolean(message.streaming)}
                />
              ) : (
                message.content
              )}
              {message.role === 'user' && (
                <span className="mt-1 flex items-center justify-end gap-1">
                  <CopyButton value={message.content} label="message" />
                  <button
                    type="button"
                    onClick={() => {
                      setText(message.content);
                      setMode('edit');
                      inputRef.current?.focus();
                    }}
                    className="rounded px-1 py-0.5 text-[9.5px] text-muted-foreground hover:text-foreground"
                    title="Edit and resend"
                  >
                    Edit
                  </button>
                </span>
              )}
              {message.role === 'assistant' && !message.error && (
                <span className="mt-1 flex items-center gap-1">
                  <CopyButton value={message.content} label="reply" />
                  {!message.streaming && !busy && (
                    <button
                      type="button"
                      onClick={() => regenerate(message.id)}
                      className="rounded px-1 py-0.5 text-[9.5px] text-muted-foreground hover:text-foreground"
                      title="Regenerate"
                    >
                      Regenerate
                    </button>
                  )}
                </span>
              )}
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

        {busy && (
          <div className="rounded-xl border border-white/10 bg-white/[0.02] px-2.5 py-2">
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              {status === 'paused' ? (
                <Pause size={12} className="shrink-0 text-amber-300" />
              ) : (
                <Loader2 size={12} className="shrink-0 animate-spin" />
              )}
              <span className="min-w-0 flex-1 truncate">
                {status === 'paused' ? 'Paused — the next tool call will wait.' : progressLabel ?? 'Working on it…'}
              </span>
              <div className="flex shrink-0 items-center gap-1">
                {status === 'running' && (
                  <button
                    type="button"
                    onClick={() => void pause()}
                    title="Pause"
                    className="rounded border border-white/10 p-1 text-muted-foreground hover:text-foreground"
                  >
                    <Pause size={9} />
                  </button>
                )}
                {status === 'paused' && (
                  <button
                    type="button"
                    onClick={() => void resume()}
                    title="Resume"
                    className="rounded border border-emerald-500/30 bg-emerald-500/10 p-1 text-emerald-300 hover:bg-emerald-500/15"
                  >
                    <Play size={9} />
                  </button>
                )}
                <button
                  type="button"
                  onClick={cancel}
                  title="Stop"
                  className="rounded border border-rose-500/25 p-1 text-rose-300 hover:bg-rose-500/10"
                >
                  <Square size={8} />
                </button>
              </div>
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

        {toolApproval && (
          <div className="rounded-xl border border-primary/30 bg-primary/[0.06] p-2.5">
            <p className="text-[11px] font-semibold text-foreground">Approval needed</p>
            <p className="mt-0.5 text-[10.5px] leading-relaxed text-muted-foreground">
              {toolApproval.summary}
            </p>
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              {toolApproval.effect} · {toolApproval.risk} risk
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                onClick={() => void decideToolApproval(true, false)}
                className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300 hover:bg-emerald-500/15"
              >
                Allow once
              </button>
              {toolApproval.grantPattern && toolApproval.risk !== 'high' && (
                <button
                  type="button"
                  onClick={() => void decideToolApproval(true, true)}
                  className="rounded-lg border border-emerald-500/20 px-2.5 py-1 text-[11px] text-emerald-200/90 hover:bg-emerald-500/10"
                >
                  Always allow
                </button>
              )}
              <button
                type="button"
                onClick={() => void decideToolApproval(false, false)}
                className="rounded-lg border border-rose-500/25 px-2.5 py-1 text-[11px] text-rose-200 hover:bg-rose-500/10"
              >
                Deny
              </button>
            </div>
          </div>
        )}

        {clarification && (
          <div className="rounded-xl border border-primary/25 bg-primary/[0.05] p-2.5">
            <p className="text-[11px] font-semibold text-foreground">One detail needed</p>
            <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{clarification.question}</p>
            <div className="mt-2 flex items-center gap-1.5">
              <input
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    submitAnswer();
                  }
                }}
                placeholder="Your answer…"
                className="min-w-0 flex-1 rounded-lg border border-white/10 bg-background/60 px-2 py-1 text-[11px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-primary/40"
              />
              <button
                type="button"
                onClick={submitAnswer}
                disabled={!answer.trim()}
                className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300 disabled:opacity-40"
              >
                Answer
              </button>
              <button
                type="button"
                onClick={() => void answerClarification('Use your best judgement.')}
                className="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground"
              >
                Decide for me
              </button>
            </div>
          </div>
        )}

        {proposal && (
          <div className="rounded-xl border border-primary/25 bg-primary/[0.05] p-2.5">
            <p className="text-[11px] font-semibold text-foreground">
              {approval ? 'Approval needed' : 'Proposed change'}
            </p>
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              {approval
                ? `${approval.effect} · ${approval.risk} risk · applies as one undo step`
                : 'Applies as one undo step'}
            </p>
            <ul className="mt-1.5 space-y-1">
              {proposal.ops.slice(0, 30).map((item, index) => (
                <li key={`${item.op}-${index}`} className="flex items-start gap-1.5 text-[10.5px] text-muted-foreground">
                  <Check size={10} className="mt-0.5 shrink-0 text-emerald-400" />
                  <span>{describeOp(item)}</span>
                </li>
              ))}
            </ul>
            {proposal.warnings.length > 0 && (
              <ul className="mt-1.5 space-y-0.5">
                {proposal.warnings.slice(0, 4).map((warning) => (
                  <li key={warning} className="flex items-start gap-1.5 text-[10px] text-amber-300">
                    <WarningCircle size={10} className="mt-0.5 shrink-0" />
                    <span>{warning}</span>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {approval && approvalBlocked ? (
                <>
                  <span className="text-[10.5px] text-rose-300">
                    This exact change was already denied. Ask for a different change.
                  </span>
                  <button
                    type="button"
                    onClick={discardPending}
                    className="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                  >
                    Dismiss
                  </button>
                </>
              ) : approval ? (
                <>
                  <button
                    type="button"
                    onClick={() => void decidePending(true, false)}
                    className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300 transition-colors hover:bg-emerald-500/15"
                  >
                    Allow once
                  </button>
                  {approval.grantPattern && approval.risk !== 'high' && (
                    <button
                      type="button"
                      onClick={() => void decidePending(true, true)}
                      className="rounded-lg border border-emerald-500/20 px-2.5 py-1 text-[11px] text-emerald-200/90 transition-colors hover:bg-emerald-500/10"
                    >
                      Always allow
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void decidePending(false, false)}
                    className="rounded-lg border border-rose-500/25 px-2.5 py-1 text-[11px] text-rose-200 transition-colors hover:bg-rose-500/10"
                  >
                    Deny
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => applyPending()}
                    className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300 transition-colors hover:bg-emerald-500/15"
                  >
                    Apply {proposal.ops.length} change{proposal.ops.length === 1 ? '' : 's'}
                  </button>
                  <button
                    type="button"
                    onClick={discardPending}
                    className="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                  >
                    Discard
                  </button>
                </>
              )}
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
                if (last) void send(last.content, mode, modelChoice);
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
        <div className="mb-1.5 flex flex-wrap items-center gap-1">
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
              : 'Every edit becomes an approval card before it touches the canvas'}
            className={cn(
              'ml-1 rounded border px-1.5 py-0.5 text-[9px] font-medium transition-colors',
              autoApply
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                : 'border-white/10 text-muted-foreground hover:text-foreground',
            )}
          >
            Auto-apply
          </button>
          <div className="ml-auto flex items-center gap-1.5">
            <ModelSelector state={chatModel} />
            <span className="text-[9px] text-muted-foreground/70">
              {runId ? `${status} · ` : ''}{selectedCount > 0 ? `${selectedCount} selected · ` : ''}Enter to send
            </span>
          </div>
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
          {status === 'paused' ? (
            <button
              type="button"
              onClick={() => void resume()}
              title="Resume"
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-emerald-500/15 text-emerald-300 transition-colors hover:bg-emerald-500/25"
            >
              <Play size={12} />
            </button>
          ) : status === 'running' ? (
            <button
              type="button"
              onClick={() => void pause()}
              title="Pause"
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-amber-500/15 text-amber-300 transition-colors hover:bg-amber-500/25"
            >
              <Pause size={12} />
            </button>
          ) : status === 'awaiting_approval' ? (
            <span
              title="Waiting for an approval decision"
              className="flex h-6 shrink-0 items-center rounded-md bg-primary/15 px-2 text-[9.5px] font-medium text-primary"
            >
              approval
            </span>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={!text.trim()}
              title="Send"
              className={cn(
                'flex h-6 w-6 shrink-0 items-center justify-center rounded-md transition-colors',
                text.trim()
                  ? 'bg-primary text-primary-foreground hover:opacity-90'
                  : 'bg-white/5 text-muted-foreground',
              )}
            >
              <ArrowUp size={12} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
