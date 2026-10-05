"use client";

// ── Message navigation rail ─────────────────────────────────────────────────
// A thin, always-visible index on the right edge of the transcript, one tick per
// USER turn. Clicking a tick scrolls that turn to the top; the tick nearest the
// reading position is highlighted, and hovering shows a short preview. It is a
// pure view over the already-rendered messages — it holds no conversation state
// and never mutates the transcript.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";
import type { Message } from "@/types/chat";

/** Only turns with real text are worth an index tick. */
function previewOf(content: string, max = 56): string {
  const flat = content.replace(/\s+/g, " ").trim();
  if (flat.length <= max) return flat;
  return `${flat.slice(0, max - 1).trimEnd()}…`;
}

/** A turn's top offset relative to the transcript's scroll origin. */
function topWithin(el: HTMLElement, node: HTMLElement): number {
  return node.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop;
}

function nodeFor(el: HTMLElement, id: string): HTMLElement | null {
  return el.querySelector<HTMLElement>(`[data-message-id="${CSS.escape(id)}"]`);
}

/** One tick is not navigation — show the rail only once there is somewhere to go. */
const MAX_TICKS = 14;

/**
 * The hover preview, portaled to `document.body`. The rail lives under a
 * `-translate-y-1/2` ancestor, and a CSS transform creates a backdrop root that
 * silently kills `backdrop-filter` on any descendant — so the glass would render
 * flat. Rendering it at body level lets it blur the real page (UI skill rule #3).
 */
function HoverPreview({ label, top, right }: { label: string; top: number; right: number }) {
  if (typeof document === "undefined") return null;
  return createPortal(
    <span
      role="tooltip"
      style={{ top, right }}
      className="pointer-events-none fixed z-50 max-w-[260px] truncate whitespace-nowrap glass-tooltip px-2.5 py-1.5 text-[11px] leading-tight text-foreground"
    >
      {label}
    </span>,
    document.body,
  );
}

export function MessageRail({
  messages,
  scrollRef,
  className,
}: {
  messages: Message[];
  /** The scrollable transcript element the rail navigates. */
  scrollRef: React.RefObject<HTMLDivElement | null>;
  className?: string;
}) {
  const userTurns = useMemo(() => messages.filter((m) => m.role === "user"), [messages]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [hoverAt, setHoverAt] = useState<{ top: number; right: number } | null>(null);
  const frame = useRef<number | null>(null);

  // Which user turn is at the reading position (the last one whose top has
  // scrolled to/above a small offset from the viewport top).
  const measure = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const anchor = el.scrollTop + 96;
    let current: string | null = null;
    for (const msg of userTurns) {
      const node = nodeFor(el, msg.id);
      if (!node) continue;
      if (topWithin(el, node) <= anchor) current = msg.id;
      else break;
    }
    setActiveId(current ?? userTurns[0]?.id ?? null);
  }, [scrollRef, userTurns]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      if (frame.current != null) return;
      frame.current = requestAnimationFrame(() => {
        frame.current = null;
        measure();
      });
    };
    measure();
    el.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      el.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame.current != null) cancelAnimationFrame(frame.current);
    };
  }, [scrollRef, measure]);

  const jumpTo = (id: string) => {
    const el = scrollRef.current;
    if (!el) return;
    const node = nodeFor(el, id);
    if (!node) return;
    el.scrollTo({ top: Math.max(0, topWithin(el, node) - 12), behavior: "smooth" });
  };

  // Show the rail as soon as there is a turn to jump back to.
  if (userTurns.length < 1) return null;

  // Bound the rail like an editor minimap: when a conversation is long, show a
  // window of turns centred on the reading position instead of one tick per turn
  // (which would overflow the viewport and clip). The window still spans every
  // region as the user scrolls, so nothing becomes unreachable.
  const activeIdx = Math.max(0, userTurns.findIndex((m) => m.id === activeId));
  let start = 0;
  if (userTurns.length > MAX_TICKS) {
    start = Math.min(
      Math.max(0, activeIdx - Math.floor(MAX_TICKS / 2)),
      userTurns.length - MAX_TICKS,
    );
  }
  const visible = userTurns.slice(start, start + MAX_TICKS);

  return (
    <nav
      aria-label="Jump to message"
      className={cn(
        "pointer-events-none absolute right-2 top-1/2 z-20 flex -translate-y-1/2 flex-col items-end gap-[3px] py-1",
        className,
      )}
    >
      {visible.map((msg) => {
        const active = msg.id === activeId;
        const hovering = msg.id === hoverId;
        const label = previewOf(msg.content);
        return (
          <div
            key={msg.id}
            className="pointer-events-auto relative flex items-center justify-end py-[1px]"
            onMouseEnter={(e) => {
              setHoverId(msg.id);
              const r = e.currentTarget.getBoundingClientRect();
              setHoverAt({ top: r.top + r.height / 2, right: window.innerWidth - r.left + 8 });
            }}
            onMouseLeave={() => {
              setHoverId((h) => (h === msg.id ? null : h));
              setHoverAt(null);
            }}
          >
            <button
              type="button"
              onClick={() => jumpTo(msg.id)}
              aria-current={active ? "true" : undefined}
              aria-label={`Jump to: ${label || "message"}`}
              className={cn(
                "block h-[2px] rounded-none transition-all duration-150 ease-out cursor-pointer",
                // Neutral grey ticks — no brand accent. WIDTH grows only on
                // HOVER; the active/reading tick stays its size and only
                // brightens to the foreground grey.
                "w-2.5 bg-muted-foreground/50",
                hovering && "w-3.5 bg-foreground/80",
                active && !hovering && "bg-foreground/70",
              )}
            />
          </div>
        );
      })}

      {hoverId && hoverAt && (() => {
        const msg = userTurns.find((m) => m.id === hoverId);
        const label = msg ? previewOf(msg.content) : "";
        return label ? <HoverPreview label={label} top={hoverAt.top} right={hoverAt.right} /> : null;
      })()}
    </nav>
  );
}
