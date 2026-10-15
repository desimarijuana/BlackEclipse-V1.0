'use client';

import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, ArrowDown, Clock, Cpu, Pencil, RotateCcw, Check, X, Copy, ThumbsUp, ThumbsDown } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { Message } from '@/types/chat';
import { Markdown } from './markdown';
import { ResponseView } from '@/components/response/response-view';
import { hasResponseFence } from '@/lib/response/parse';
import { planMarkdown, plannerUpgraded } from '@/lib/response/planner';
import { ResponseStatusLine } from './response-status';
import { ActivityFeed } from './activity-feed';
import { ChangeCards } from './change-cards';
import { ResearchEvidencePanel } from './research-evidence-panel';
import { VisionPanel } from './vision-panel';
import { ImageGalleryPanel } from './image-gallery';
import { DocumentPanel } from './document-panel';
import { MemoryActionPanel } from './memory-action-panel';
import { ChatCapabilityPanel } from './chat-capability-panel';
import { ComputedResultPanel } from './computed-result-panel';
import { MessageRail } from './message-rail';

interface ChatHistoryProps {
  messages: Message[];
  /**
   * `false` (default) is the full-page ChatBot layout (centered wide column,
   * user bubbles only — assistant text renders wide like a code agent).
   * `true` fills a narrow container (e.g. the floating ChatDock) edge-to-edge.
   */
  compact?: boolean;
  /**
   * Called when the user edits a previously-sent prompt. The caller decides
   * what "editing" means (typically: truncate the thread at that message and
   * re-send) — the component only reports the new text.
   */
  onEditMessage?: (id: string, content: string) => void;
  /** Re-send a user prompt as-is (the "redirect" action on a user bubble). */
  onResendMessage?: (id: string) => void;
  /** Retry a failed assistant turn (re-runs its preceding user prompt). */
  onRetryMessage?: (id: string) => void;
  /** Rate an assistant turn. The caller persists the choice on the message. */
  onFeedback?: (id: string, feedback: 'up' | 'down') => void;
  /** Run a follow-up agent turn (used by response `controls` blocks). */
  onFollowup?: (prompt: string) => void;
}

/** How close to the bottom counts as "following the stream". */
const NEAR_BOTTOM_PX = 96;

/** Compact, honest turn duration: "820ms", "2.3s", "1m 5s". */
function formatTurnDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.round((ms % 60_000) / 1000);
  return `${m}m ${s}s`;
}

/**
 * Assistant prose is the expensive part to render (full Markdown parse). It only
 * changes when its text does, so memoizing it stops a streaming turn from
 * re-parsing every *other* turn in the transcript.
 *
 * When a settled answer contains a structured response fence, `Markdown` renders
 * it inline. When it does not, the deterministic planner re-presents plain
 * Markdown (tables → interactive tables, source lists → citations) without
 * changing the words. While streaming, it falls back to raw Markdown so a
 * half-written block never flickers into a structured render.
 */
const AssistantContent = memo(function AssistantContent({
  content,
  compact,
  streaming,
  onFollowup,
}: {
  content: string;
  compact: boolean;
  streaming: boolean;
  onFollowup?: (prompt: string) => void;
}) {
  const planned = useMemo(() => {
    if (streaming || hasResponseFence(content)) return null;
    const response = planMarkdown(content);
    return plannerUpgraded(response) ? response : null;
  }, [content, streaming]);

  if (planned) {
    return <ResponseView response={planned} compact={compact} onFollowup={onFollowup} />;
  }
  return <Markdown content={content} compact={compact} streaming={streaming} onFollowup={onFollowup} className="w-full" />;
});

export function ChatHistory({ messages, compact = false, onEditMessage, onResendMessage, onRetryMessage, onFeedback, onFollowup }: ChatHistoryProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  // The "Latest" pill is portaled to <body> so its backdrop-filter samples the
  // real page. The transcript sits inside the app shell's own `.glass-card`,
  // which is a backdrop root and would silently flatten a nested glass surface —
  // and a CSS transform on an ancestor does the same. This tracks the
  // transcript's on-screen box so the portaled pill can be positioned over it.
  const [rootRect, setRootRect] = useState<{ left: number; top: number; width: number; bottom: number } | null>(null);

  // Track whether the viewport is pinned to the bottom. When it is, we follow the
  // stream and hide the scrollbar; when the user scrolls up we reveal the
  // scrollbar and a "jump to latest" button so the thread still reads scrollable.
  const [atBottom, setAtBottom] = useState(true);
  const atBottomRef = useRef(true);
  // A short custom scroll indicator. The native transcript bar spans the FULL
  // height of the scroll container, which reads as a long band running down the
  // right edge and under the header. It is hidden and replaced by this compact
  // thumb (capped at ~28% of the track) that tracks the reading position.
  const [bar, setBar] = useState<{ top: number; height: number } | null>(null);
  // The thumb is an auto-hiding overlay: it appears while scrolling, hovering the
  // transcript or dragging, then fades out when idle.
  const [barVisible, setBarVisible] = useState(false);
  const barHideTimer = useRef<number | null>(null);
  const barDraggingRef = useRef(false);
  // True while the transcript is scrolled by code (auto-follow), so those scroll
  // events don't reveal the scrollbar.
  const programmaticScrollRef = useRef(false);
  const clearBarTimer = useCallback(() => {
    if (barHideTimer.current != null) {
      window.clearTimeout(barHideTimer.current);
      barHideTimer.current = null;
    }
  }, []);
  const scheduleBarHide = useCallback((delay = 1200) => {
    clearBarTimer();
    barHideTimer.current = window.setTimeout(() => {
      if (!barDraggingRef.current) setBarVisible(false);
    }, delay);
  }, [clearBarTimer]);
  const revealBar = useCallback(() => {
    setBarVisible(true);
    scheduleBarHide();
  }, [scheduleBarHide]);
  useEffect(() => () => clearBarTimer(), [clearBarTimer]);
  const updateBar = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const { scrollTop, scrollHeight, clientHeight } = el;
    const overflow = scrollHeight - clientHeight;
    if (overflow <= 1) { setBar(null); return; }
    const height = Math.max(28, Math.min(clientHeight * 0.28, clientHeight * (clientHeight / scrollHeight)));
    const top = (scrollTop / overflow) * (clientHeight - height);
    setBar({ top, height });
  }, []);
  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const next = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    atBottomRef.current = next;
    setAtBottom(next);
    updateBar();
    // Auto-follow (new/streamed messages) moves the transcript programmatically;
    // that is not "using" the scrollbar, so it must not reveal it. Only genuine
    // user scrolling/dragging does.
    if (!programmaticScrollRef.current) revealBar();
  }, [updateBar, revealBar]);

  const scrollToBottom = useCallback((smooth = false) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
    atBottomRef.current = true;
    setAtBottom(true);
  }, []);

  // Drag the custom scroll thumb: the transcript hides the native bar
  // (`scrollbar-hide`), so this thumb IS the scrollbar — it must be grabbable,
  // not just an indicator, or scrolling reads as broken.
  const [barDragging, setBarDragging] = useState(false);
  const onBarPointerDown = useCallback((e: { clientY: number; preventDefault: () => void }) => {
    const el = scrollRef.current;
    if (!el || !bar) return;
    const track = el.clientHeight - bar.height;
    const overflow = el.scrollHeight - el.clientHeight;
    if (track <= 0 || overflow <= 0) return;
    e.preventDefault();
    const startY = e.clientY;
    const startTop = el.scrollTop;
    setBarDragging(true);
    barDraggingRef.current = true;
    revealBar();
    const move = (ev: PointerEvent) => {
      const delta = ev.clientY - startY;
      el.scrollTop = startTop + (delta / track) * overflow;
      onScroll();
    };
    const up = () => {
      setBarDragging(false);
      barDraggingRef.current = false;
      scheduleBarHide(500);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
      document.body.style.userSelect = '';
    };
    document.body.style.userSelect = 'none';
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
  }, [bar, onScroll, revealBar, scheduleBarHide]);

  useEffect(() => {
    if (!atBottomRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    programmaticScrollRef.current = true;
    el.scrollTop = el.scrollHeight;
    // Clear on the next frame, after the resulting scroll event has fired.
    const id = requestAnimationFrame(() => { programmaticScrollRef.current = false; });
    return () => cancelAnimationFrame(id);
  }, [messages]);

  // Keep the thumb's size/position current on layout changes. It stays HIDDEN
  // here (no `revealBar()`) — the scrollbar only appears once the user actually
  // scrolls or drags it.
  useLayoutEffect(() => {
    updateBar();
  }, [updateBar, messages]);

  // Keep the portaled "Latest" pill aligned with the transcript box, and keep
  // the short scroll thumb sized to the (possibly resized) transcript.
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      setRootRect({ left: r.left, top: r.top, width: r.width, bottom: r.bottom });
      updateBar();
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    if (scrollRef.current) observer.observe(scrollRef.current);
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [messages, updateBar]);

  const startEdit = (msg: Message) => {
    setEditingId(msg.id);
    setDraft(msg.content);
  };

  const commitEdit = () => {
    if (editingId && draft.trim()) onEditMessage?.(editingId, draft.trim());
    setEditingId(null);
  };

  const copyMessage = async (msg: Message) => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopiedId(msg.id);
      setTimeout(() => setCopiedId((c) => (c === msg.id ? null : c)), 1500);
    } catch {
      // Clipboard unavailable — leave the button unchanged.
    }
  };

  return (
    <div
      ref={rootRef}
      className="relative flex-1 min-h-0 w-full"
      style={{ fontFamily: 'var(--chat-font, var(--font-sans))' }}
    >
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className={cn(
          'h-full w-full overflow-y-auto min-h-0 scrollbar-hide',
          compact ? 'space-y-3 p-3 pr-1.5' : 'px-4 md:px-6 pr-3 md:pr-5 space-y-6 pb-6',
        )}
      >
      <div className={compact ? 'space-y-3' : 'space-y-6'}>
        {messages.map((msg) => {
          const working = msg.role === 'assistant' && msg.status != null && msg.status !== 'completed';
          return (
            <div
              key={msg.id}
              data-message-id={msg.id}
              className={`group animate-fade-in-up flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
            >
              {msg.role === 'assistant' && msg.status != null && !(msg.activities && msg.activities.length > 0) && (
                <div className={cn(msg.content ? 'mb-2' : '')}>
                  <ResponseStatusLine status={msg.status} activities={msg.activities} compact={compact} />
                </div>
              )}

              {msg.role === 'assistant' && ((msg.activities && msg.activities.length > 0) || Boolean(msg.autonomy) || Boolean(msg.codeVerification) || Boolean(msg.capability)) && (
                <ActivityFeed
                  activities={msg.activities ?? []}
                  status={msg.status}
                  compact={compact}
                  capability={{ autonomy: msg.autonomy, verification: msg.codeVerification, capability: msg.capability }}
                />
              )}

              {msg.role === 'assistant' ? (
                <>
                  {msg.error && (
                    <div
                      role="alert"
                      className="w-full rounded-xl border border-rose-500/30 bg-rose-500/[0.06] px-3 py-2.5 text-[13px] text-rose-200/90"
                    >
                      <div className="flex items-start gap-2">
                        <AlertTriangle size={14} className="mt-0.5 shrink-0 text-rose-400" />
                        <div className="min-w-0 flex-1">
                          <p className="break-words">{msg.error.message}</p>
                          {onRetryMessage && (
                            <button
                              type="button"
                              onClick={() => onRetryMessage(msg.id)}
                              className="mt-2 inline-flex items-center gap-1 rounded-full border border-rose-500/30 px-2.5 py-1 text-[11px] font-medium text-rose-200 transition-colors hover:bg-rose-500/10 cursor-pointer"
                            >
                              <RotateCcw size={11} /> Retry
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                  {msg.changes && msg.changes.length > 0 && (
                    <ChangeCards changes={msg.changes} compact={compact} />
                  )}
                  {msg.content && <AssistantContent content={msg.content} compact={compact} streaming={working} onFollowup={onFollowup} />}
                  <ChatCapabilityPanel
                    autonomy={msg.autonomy}
                    verification={msg.codeVerification}
                    runId={msg.runId}
                    compact={compact}
                  />
                  {(msg.analysis || msg.research) && (
                    <div className="mt-3 flex w-full flex-col gap-3 md:flex-row md:items-start">
                      {msg.analysis ? (
                        <div className="w-full md:w-1/2 md:min-w-0 [&>div]:mt-0">
                          <ComputedResultPanel result={msg.analysis} compact={compact} />
                        </div>
                      ) : null}
                      {msg.research ? (
                        <div className="w-full md:w-1/2 md:min-w-0 [&>div]:mt-0">
                          <ResearchEvidencePanel research={msg.research} compact={compact} />
                        </div>
                      ) : null}
                    </div>
                  )}
                  {msg.vision ? (
                    <VisionPanel vision={msg.vision} compact={compact} />
                  ) : null}
                  {msg.images ? (
                    <ImageGalleryPanel images={msg.images} compact={compact} />
                  ) : null}
                  {msg.documents ? (
                    <DocumentPanel documents={msg.documents} compact={compact} />
                  ) : null}
                  {msg.memory ? (
                    <MemoryActionPanel memory={msg.memory} runId={msg.runId} compact={compact} />
                  ) : null}
                  {!working && (msg.content || msg.model?.model || msg.durationMs != null) && (
                    <div className="hover-reveal mt-1 flex w-full flex-wrap items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                      {msg.durationMs != null && (
                        <span
                          className={cn(
                            'inline-flex items-center gap-1 font-mono text-muted-foreground/60 tabular-nums',
                            compact ? 'text-[10px]' : 'text-[11px]',
                          )}
                          title="Time this reply took"
                        >
                          <Clock size={compact ? 10 : 11} className="shrink-0 opacity-70" />
                          {formatTurnDuration(msg.durationMs)}
                        </span>
                      )}
                      {msg.content && (
                        <>
                          <button
                            type="button"
                            onClick={() => void copyMessage(msg)}
                            className="flex items-center gap-1 rounded-full px-2 py-1 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer"
                            title="Copy response"
                            aria-label="Copy response"
                          >
                            {copiedId === msg.id ? <Check size={11} /> : <Copy size={11} />}
                            {copiedId === msg.id ? 'Copied' : 'Copy'}
                          </button>
                          {onRetryMessage && (
                            <button
                              type="button"
                              onClick={() => onRetryMessage(msg.id)}
                              className="flex items-center gap-1 rounded-full px-2 py-1 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer"
                              title="Regenerate response"
                              aria-label="Regenerate response"
                            >
                              <RotateCcw size={11} /> Regenerate
                            </button>
                          )}
                          {onFeedback && (
                            <span className="ml-0.5 flex items-center gap-0.5 border-l border-border/40 pl-1.5">
                              <button
                                type="button"
                                onClick={() => onFeedback(msg.id, 'up')}
                                aria-pressed={msg.feedback === 'up'}
                                className={cn(
                                  'rounded-full p-1.5 transition-colors cursor-pointer hover:bg-accent',
                                  msg.feedback === 'up' ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
                                )}
                                title="Good response"
                                aria-label="Good response"
                              >
                                <ThumbsUp size={11} />
                              </button>
                              <button
                                type="button"
                                onClick={() => onFeedback(msg.id, 'down')}
                                aria-pressed={msg.feedback === 'down'}
                                className={cn(
                                  'rounded-full p-1.5 transition-colors cursor-pointer hover:bg-accent',
                                  msg.feedback === 'down' ? 'text-rose-400' : 'text-muted-foreground hover:text-foreground',
                                )}
                                title="Bad response"
                                aria-label="Bad response"
                              >
                                <ThumbsDown size={11} />
                              </button>
                            </span>
                          )}
                        </>
                      )}
                      {msg.model?.model && (
                        <div
                          className={cn(
                            'ml-auto inline-flex max-w-full items-center gap-1.5 font-mono text-muted-foreground/70',
                            compact ? 'text-[10px]' : 'text-[11px]',
                          )}
                          title={`Answered by ${msg.model.model}${msg.model.provider ? ` · ${msg.model.provider}` : ''}`}
                        >
                          <Cpu size={compact ? 10 : 11} className="shrink-0 text-primary/60" />
                          <span className="truncate">{msg.model.model}</span>
                          {msg.model.provider && (
                            <>
                              <span className="text-muted-foreground/40">·</span>
                              <span className="truncate text-muted-foreground/50">{msg.model.provider}</span>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </>
              ) : editingId === msg.id ? (
                <div className="w-full flex flex-col gap-2">
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Escape') setEditingId(null);
                      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) commitEdit();
                    }}
                    autoFocus
                    rows={Math.min(8, Math.max(2, draft.split('\n').length))}
                    className="w-full resize-none rounded-2xl border border-primary/40 bg-card px-4 py-3 text-[14px] md:text-[15px] leading-relaxed text-foreground outline-none focus:ring-1 focus:ring-primary"
                  />
                  <div className="flex items-center justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setEditingId(null)}
                      className="flex items-center gap-1 rounded-full px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer"
                    >
                      <X size={13} /> Cancel
                    </button>
                    <button
                      type="button"
                      onClick={commitEdit}
                      disabled={!draft.trim()}
                      className="flex items-center gap-1 rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors cursor-pointer"
                    >
                      <Check size={13} /> Resend
                    </button>
                  </div>
                </div>
              ) : (
                <div className={cn('group flex flex-col', 'items-end', 'w-full')}>
                  <div className={cn(
                    // `.chat-bubble` paints a scheme-aware fill from
                    // `--chat-bubble-bg-light/-dark` (Settings › ChatBot Page ›
                    // Chat background › Prompt bubble), defaulting to a neutral
                    // tint that reads on both the light and dark chat surfaces.
                    'chat-bubble leading-relaxed break-words whitespace-pre-wrap text-foreground',
                    compact
                      ? 'px-2.5 py-1.5 max-w-[90%] text-[12px] rounded-2xl'
                      // Grow with the text up to the full column width: short
                      // prompts stay a compact pill, long ones use every pixel
                      // instead of wrapping early inside a fixed-size bubble.
                      : 'w-fit max-w-full px-3.5 py-2 md:px-4 md:py-2.5 text-[13px] md:text-[14px] rounded-2xl',
                  )}>
                    {msg.content}
                  </div>
                  <div className="hover-reveal mt-1 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                    <button
                      type="button"
                      onClick={() => void copyMessage(msg)}
                      className="flex items-center gap-1 rounded-full px-2 py-1 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer"
                      title="Copy prompt"
                      aria-label="Copy prompt"
                    >
                      {copiedId === msg.id ? <Check size={11} /> : <Copy size={11} />}
                      {copiedId === msg.id ? 'Copied' : 'Copy'}
                    </button>
                    {onResendMessage && (
                      <button
                        type="button"
                        onClick={() => onResendMessage(msg.id)}
                        className="flex items-center gap-1 rounded-full px-2 py-1 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer"
                        title="Redirect — re-send this prompt"
                        aria-label="Redirect"
                      >
                        <RotateCcw size={11} /> Redirect
                      </button>
                    )}
                    {onEditMessage && (
                      <button
                        type="button"
                        onClick={() => startEdit(msg)}
                        className="flex items-center gap-1 rounded-full px-2 py-1 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer"
                        title="Edit prompt"
                        aria-label="Edit prompt"
                      >
                        <Pencil size={11} /> Edit
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      </div>

      {/* Custom scroll indicator — a drag-grabbable thumb (the native bar is
          hidden), inset from the edges so it never runs under the header. */}
      {bar && (
        <div
          aria-label="Scroll conversation"
          onPointerDown={onBarPointerDown}
          className={cn(
            'absolute right-1.5 z-20 w-1.5 rounded-full bg-foreground/20 cursor-grab touch-none transition-opacity duration-200 hover:bg-foreground/40',
            barDragging && 'bg-foreground/50 cursor-grabbing',
            barVisible ? 'opacity-100' : 'opacity-0 pointer-events-none',
          )}
          style={{ top: bar.top, height: bar.height }}
        />
      )}

      <MessageRail messages={messages} scrollRef={scrollRef} />

      {!atBottom && rootRect &&
        createPortal(
          <button
            type="button"
            onClick={() => scrollToBottom(true)}
            style={{
              position: 'fixed',
              left: rootRect.left + rootRect.width / 2,
              top: compact ? rootRect.bottom - 8 : rootRect.bottom - 16,
              transform: 'translate(-50%, -100%)',
            }}
            className="z-30 flex items-center gap-1.5 rounded-full glass-tooltip px-3 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:text-primary cursor-pointer animate-fade-in"
            title="Scroll to latest"
            aria-label="Scroll to latest"
          >
            <ArrowDown size={13} /> Latest
          </button>,
          document.body,
        )}
    </div>
  );
}
