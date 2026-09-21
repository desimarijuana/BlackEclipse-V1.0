'use client';

// ── ChatDock — the floating bottom composer ──────────────────────────────────
// A Gemini-style assistant bar that floats at the bottom-centre of the app.
// Mounted once in the app shell (`stock-chat.tsx`) so it appears on every tab
// EXCEPT the ChatBot and while the Settings modal is open (the shell passes
// `visible={false}` there — see `ChatDockProps.visible`); the standalone
// `/alerts` route mounts its own. Collapsed it is just the composer; once it has
// a conversation (or the user focuses it) the transcript expands ABOVE it in the
// same floating stack.
//
// It reuses the SAME chat stack as the full ChatBot tab — `ChatHistory` /
// `ChatInput`, `getAgentProvider()`, and `/api/agent/research` — so there is one
// chat implementation, not a second one. It owns its own conversation
// (`be_chat_dock_v1`) so it never fights the ChatBot tab's shell-owned state.
//
// Portaled to <body> (the app shell's glass-card backdrop-filter traps fixed
// positioning otherwise). It is NOT marked `data-keyboard-overlay` — it is
// always on screen, so marking it a blocking dialog would disable every page
// shortcut permanently; the input already blocks shortcuts while focused. It IS
// `data-nodrag` so the workspace drag engine ignores it, and sits at z-[90]
// above the Command Center fullscreen overlay (z-[80]) — so the shell's single
// instance also covers fullscreen and no per-overlay copy is needed.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ArrowUp, Maximize2, Mic, Minimize2, Minus, Plus, Sparkles, SquarePen, Trash2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { isKeyboardEventAvailable } from '@/lib/keyboard';
import { getAgentProvider } from '@/lib/agent/registry';
import type { Message } from '@/types/chat';
import { ChatHistory } from './chat-history';

const STORAGE_KEY = 'be_chat_dock_v1';
/** Persisted collapse preference — the user decides small vs big. */
const MINIMIZED_KEY = 'be_chat_dock_minimized_v1';
/** Persisted position of the minimized pill (viewport px, top-left corner). */
const PILL_POS_KEY = 'be_chat_dock_pill_pos_v1';
const MAX_PERSISTED = 60;

function loadMinimized(): boolean {
  if (typeof window === 'undefined') return false;
  try { return window.localStorage.getItem(MINIMIZED_KEY) === '1'; } catch { return false; }
}

function saveMinimized(minimized: boolean) {
  try { window.localStorage.setItem(MINIMIZED_KEY, minimized ? '1' : '0'); } catch { /* best effort */ }
}

interface PillPos { x: number; y: number; }

function loadPillPos(): PillPos | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(PILL_POS_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as Partial<PillPos>;
    if (typeof p.x !== 'number' || typeof p.y !== 'number' || !Number.isFinite(p.x) || !Number.isFinite(p.y)) return null;
    return { x: p.x, y: p.y };
  } catch { return null; }
}

function savePillPos(pos: PillPos) {
  try { window.localStorage.setItem(PILL_POS_KEY, JSON.stringify(pos)); } catch { /* best effort */ }
}

/** Keep the pill fully on screen after a drag or a viewport resize. */
function clampPill(x: number, y: number, w: number, h: number): PillPos {
  const pad = 6;
  const maxX = Math.max(pad, window.innerWidth - w - pad);
  const maxY = Math.max(pad, window.innerHeight - h - pad);
  return { x: Math.min(Math.max(pad, x), maxX), y: Math.min(Math.max(pad, y), maxY) };
}

function loadMessages(): Message[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (m): m is Message =>
        m && typeof m.id === 'string' && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string',
    );
  } catch { return []; }
}

function saveMessages(messages: Message[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-MAX_PERSISTED)));
  } catch { /* best effort */ }
}

function newId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

/** The configured provider's real label (never a fabricated model name). */
function useProviderLabel(): string {
  return React.useMemo(() => getAgentProvider().label, []);
}

export interface ChatDockProps {
  /** Extra classes for the floating stack (e.g. to clear the fullscreen Exit). */
  className?: string;
  /** Placeholder for the composer. */
  placeholder?: string;
  /** Accessible label. */
  title?: string;
  /**
   * Whether this surface is allowed to show the dock. The host passes `false`
   * on the ChatBot tab and while the Settings modal is open; the dock still
   * gates on its host panel's own display. Kept mounted (not conditionally
   * rendered) so the conversation/expansion survives a suppress → restore.
   */
  visible?: boolean;
}

export function ChatDock({
  className,
  placeholder = 'Ask a question or start a project…',
  title = 'Assistant',
  visible = true,
}: ChatDockProps) {
  const [mounted, setMounted] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  // Manual expand/collapse of the transcript (independent of focus, so the user
  // can scroll back through an answer without the panel collapsing).
  const [expanded, setExpanded] = useState(false);
  // True minimize: the whole dock shrinks to a small pill the user can restore.
  // Persisted so the choice survives a reload.
  const [minimized, setMinimized] = useState(false);
  // The minimized pill is draggable; `null` means "default corner" (bottom-right).
  const [pillPos, setPillPos] = useState<PillPos | null>(null);
  const pillRef = useRef<HTMLButtonElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const providerLabel = useProviderLabel();

  // The Command Center is a KEEP-ALIVE tab: once visited it stays mounted and is
  // hidden with `display:none`. A portal to <body> is NOT hidden by an ancestor
  // `display:none`, so without this the dock would float over every other tab.
  // Gate on the host tab's own display via a MutationObserver — NOT an
  // IntersectionObserver (the dashboard scrolls; an intersection test on a
  // zero-size sentinel reported "hidden" mid-scroll and made the dock vanish).
  const [hostVisible, setHostVisible] = useState(false);
  const sentinelRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    setMounted(true);
    setMessages(loadMessages());
    setMinimized(loadMinimized());
    setPillPos(loadPillPos());
  }, []);

  // Re-clamp the pill if the window shrinks under it.
  useEffect(() => {
    if (!pillPos) return;
    const onResize = () => {
      const el = pillRef.current;
      const r = el?.getBoundingClientRect();
      setPillPos(p => (p ? clampPill(p.x, p.y, r?.width ?? 130, r?.height ?? 36) : p));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [pillPos]);

  const toggleMinimized = useCallback(() => {
    setMinimized(prev => {
      const next = !prev;
      saveMinimized(next);
      if (next) setExpanded(false);
      else setTimeout(() => textareaRef.current?.focus(), 0);
      return next;
    });
  }, []);

  /**
   * Pointer drag for the minimized pill. A press that moves past a small
   * threshold becomes a drag (position persisted); otherwise it is a click that
   * restores the dock. Uses real pointer captures so the drag survives leaving
   * the button.
   */
  const onPillPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    const el = pillRef.current;
    if (!el) return;
    e.preventDefault();
    const start = el.getBoundingClientRect();
    const rect = { w: start.width, h: start.height };
    const startX = e.clientX;
    const startY = e.clientY;
    const originX = start.left;
    const originY = start.top;
    let moved = false;
    let latest = clampPill(originX, originY, rect.w, rect.h);
    const PID = e.pointerId;

    const onMove = (ev: PointerEvent) => {
      if (ev.pointerId !== PID) return;
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      if (!moved && Math.hypot(dx, dy) < 4) return;
      moved = true;
      latest = clampPill(originX + dx, originY + dy, rect.w, rect.h);
      // Move the live element directly for a jank-free drag; commit on release.
      el.style.left = `${latest.x}px`;
      el.style.top = `${latest.y}px`;
      el.style.right = 'auto';
      el.style.bottom = 'auto';
    };
    const onUp = (ev: PointerEvent) => {
      if (ev.pointerId !== PID) return;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      if (moved) {
        setPillPos(latest);
        savePillPos(latest);
      } else {
        // A click (no drag) restores the dock.
        toggleMinimized();
      }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
  };

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) { setHostVisible(true); return; }
    // Gate on the HOST TAB's visibility, never on viewport intersection: the
    // dashboard scrolls, so an intersection test on a zero-size sentinel reports
    // "not visible" mid-scroll and made the composer vanish. Walk up to the
    // keep-alive panel and read its own display/visibility (the same test the
    // keyboard layer uses), re-reading whenever the tab toggles `hidden`.
    const panel = el.closest<HTMLElement>('[data-keepalive-panel]') ?? el.parentElement;
    if (!panel) { setHostVisible(true); return; }
    const read = () => {
      const style = getComputedStyle(panel);
      const painted = typeof panel.getClientRects === 'function' && panel.getClientRects().length > 0;
      setHostVisible(painted && style.display !== 'none' && style.visibility !== 'hidden');
    };
    read();
    if (typeof MutationObserver === 'undefined') return;
    const mo = new MutationObserver(read);
    mo.observe(panel, { attributes: true, attributeFilter: ['class', 'style'] });
    return () => mo.disconnect();
  }, [mounted]);

  // A conversation always shows its transcript, regardless of focus.
  const showTranscript = (expanded || messages.length > 0 || busy) && !minimized;

  // Auto-grow the composer up to a cap (mirrors the reference composer).
  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);
  useEffect(() => { resize(); }, [query, resize]);

  // Collapse the transcript when dismissed with Escape (captured so it does not
  // also exit Command Center fullscreen). Only active while the panel is open.
  useEffect(() => {
    if (!showTranscript) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || !isKeyboardEventAvailable(e)) return;
      e.preventDefault();
      e.stopPropagation();
      setExpanded(false);
      textareaRef.current?.blur();
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [showTranscript]);

  const append = useCallback((next: Message[]) => {
    setMessages(next);
    saveMessages(next);
  }, []);

  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  const pushAssistant = useCallback((content: string) => {
    append([...messagesRef.current, { id: newId(), role: 'assistant', content }]);
  }, [append]);

  const newChat = useCallback(() => {
    append([]);
    setQuery('');
    setExpanded(false);
    textareaRef.current?.focus();
  }, [append]);

  const send = async () => {
    const text = query.trim();
    if (!text || busy) return;
    setQuery('');
    setExpanded(true);

    const userMsg: Message = { id: newId(), role: 'user', content: text };
    append([...messagesRef.current, userMsg]);

    setBusy(true);
    try {
      // Everything goes through the harness so the chat IS the Eclipse Agent
      // (system prompt + JDdS tools + persisted run). It picks its own tools,
      // so a research-flavored ask no longer needs a separate engine.
      const history = messagesRef.current
        .slice(0, -1)
        .map(m => ({ role: m.role, content: m.content }));
      const reply = await getAgentProvider().chat([...history, { role: 'user', content: text }]);
      pushAssistant(reply);
    } catch (err) {
      pushAssistant(`Error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  };

  const canSend = query.trim().length > 0 && !busy;

  const dock = hostVisible && visible && mounted && typeof document !== 'undefined' && createPortal(
    <div
      className={cn(
        'pointer-events-none fixed inset-x-0 bottom-3 z-[90] flex flex-col items-center px-3',
        className,
      )}
      data-nodrag
    >
      <div className="pointer-events-auto flex w-[min(560px,100%)] flex-col gap-2">
        {minimized ? (
          // Minimized: a compact pill. Click restores; drag repositions (the
          // position is persisted). Defaults to the bottom-right corner, and
          // when positioned we anchor by top/left so it never fights the layout.
          <button
            ref={pillRef}
            type="button"
            onPointerDown={onPillPointerDown}
            style={pillPos ? { left: pillPos.x, top: pillPos.y, right: 'auto', bottom: 'auto' } : undefined}
            className={cn(
              'fixed z-[90] inline-flex touch-none select-none items-center gap-2 rounded-full border border-white/12 dark:border-white/8 glass-card-strong px-3.5 py-2 text-xs font-bold text-muted-foreground shadow-2xl shadow-black/50 transition-colors hover:text-primary',
              pillPos ? 'cursor-grab active:cursor-grabbing' : 'bottom-4 right-4 ml-auto cursor-grab active:cursor-grabbing',
            )}
            title="Drag to move · click to expand"
            aria-label="Expand the assistant (drag to move)"
            aria-expanded={false}
          >
            <Sparkles size={13} className="pointer-events-none text-primary" />
            <span className="pointer-events-none hidden sm:inline">Assistant</span>
            <Maximize2 size={13} className="pointer-events-none" />
          </button>
        ) : (
          <>
        {/* Transcript — expands above the composer. */}
        {showTranscript && (
          <div
            role="dialog"
            aria-label={title}
            className="flex max-h-[min(45vh,360px)] flex-col overflow-hidden rounded-[1.75rem] border border-white/12 dark:border-white/8 glass-card-strong shadow-2xl shadow-black/50 animate-fade-in"
          >
            <div className="flex shrink-0 items-center gap-2 border-b border-border/10 px-4 py-2.5">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/15 text-primary">
                <Sparkles size={12} />
              </span>
              <p className="min-w-0 flex-1 truncate font-serif text-sm font-semibold text-foreground">{title}</p>
              <button
                type="button"
                onClick={newChat}
                className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:text-primary cursor-pointer"
                title="New chat"
              >
                <SquarePen size={13} />
              </button>
              <button
                type="button"
                onClick={() => { append([]); setExpanded(false); }}
                disabled={messages.length === 0}
                className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:text-rose-400 disabled:cursor-default disabled:opacity-30 cursor-pointer"
                title="Clear conversation"
              >
                <Trash2 size={13} />
              </button>
              <button
                type="button"
                onClick={() => { setExpanded(false); textareaRef.current?.blur(); }}
                className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
                title="Collapse"
              >
                <Minimize2 size={13} />
              </button>
            </div>

            {messages.length === 0 ? (
              <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 px-6 py-8 text-center">
                <p className="text-sm font-semibold text-foreground">Ask anything</p>
                <p className="max-w-[34ch] text-xs leading-relaxed text-muted-foreground">
                  Try “research NVDA”, “market sentiment”, or “what changed today?”.
                </p>
              </div>
            ) : (
              <ChatHistory messages={messages} compact />
            )}

            {busy && (
              <p className="flex shrink-0 items-center gap-1.5 border-t border-border/10 px-4 py-2 text-[10px] font-mono text-muted-foreground/80">
                <Sparkles size={10} className="animate-pulse text-primary" /> thinking…
              </p>
            )}
          </div>
        )}

        {/* Composer — always visible, bottom-centre. */}
        <div className="rounded-[1.75rem] border border-white/12 dark:border-white/8 glass-card-strong p-2 shadow-2xl shadow-black/50">
          <textarea
            ref={textareaRef}
            rows={1}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder={placeholder}
            aria-label={title}
            className="max-h-[200px] w-full resize-none bg-transparent px-3 pb-1 pt-2.5 text-sm leading-relaxed text-foreground outline-none scrollbar-hide placeholder:text-muted-foreground/70"
          />

          <div className="flex items-center gap-1.5 px-1">
            <button
              type="button"
              onClick={() => textareaRef.current?.focus()}
              className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
              title="Add context (coming soon)"
              aria-label="Add context"
            >
              <Plus size={17} />
            </button>
            <button
              type="button"
              onClick={() => setExpanded(v => !v)}
              className={cn(
                'flex h-9 w-9 items-center justify-center rounded-full transition-colors cursor-pointer hover:bg-accent',
                expanded ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
              )}
              title={expanded ? 'Collapse transcript' : 'Expand transcript'}
              aria-label={expanded ? 'Collapse transcript' : 'Expand transcript'}
              aria-expanded={expanded}
            >
              {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
            {/* True minimize: shrink the whole dock to a restore pill. */}
            <button
              type="button"
              onClick={toggleMinimized}
              className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
              title="Minimize"
              aria-label="Minimize assistant"
            >
              <Minus size={17} />
            </button>

            {/* Provider pill — the REAL configured provider, never a made-up model. */}
            <span
              className="ml-1 hidden items-center gap-1.5 rounded-full border border-border/25 bg-accent/25 px-2.5 py-1 text-[10px] font-bold text-muted-foreground sm:inline-flex"
              title={`Chat provider: ${providerLabel}`}
            >
              <Sparkles size={11} className="text-primary" />
              {providerLabel}
            </span>

            <div className="ml-auto flex items-center gap-1.5">
              <button
                type="button"
                className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
                title="Voice input (coming soon)"
                aria-label="Voice input"
              >
                <Mic size={17} />
              </button>
              <button
                type="button"
                onClick={() => void send()}
                disabled={!canSend}
                className={cn(
                  'flex h-9 w-9 items-center justify-center rounded-full transition-all cursor-pointer',
                  canSend
                    ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                    : 'bg-accent/40 text-muted-foreground disabled:opacity-50 cursor-not-allowed',
                )}
                title="Send"
                aria-label="Send"
              >
                {busy
                  ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary-foreground/40 border-t-primary-foreground" />
                  : <ArrowUp size={17} />}
              </button>
            </div>
          </div>
        </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  );

  return (
    <>
      {/* Visibility sentinel — stays in the host subtree so the observer sees
          the keep-alive tab's display:none. Zero-size, non-interactive. */}
      <span ref={sentinelRef} aria-hidden className="pointer-events-none absolute h-0 w-0" />
      {dock}
    </>
  );
}
