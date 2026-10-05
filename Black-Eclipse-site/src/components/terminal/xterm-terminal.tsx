"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Terminal as TerminalIcon } from "@/lib/icons";
import "@xterm/xterm/css/xterm.css";
import { cn } from "@/lib/utils";
import {
  closeTerminalSession,
  openTerminalSession,
  sendTerminalRaw,
  streamTerminalOutput,
} from "@/lib/harness/terminal-browser";

//: The backend appends a hidden sentinel line after every command to learn the
//: shell's working directory. A real terminal must not show it, so we drop those
//: lines from the DISPLAY stream (the backend already strips them from agent text).
const SENTINEL = "::ECL-ECLIPSE::cd=";
function stripSentinel(text: string): string {
  if (!text.includes(SENTINEL)) return text;
  return text
    .split(/\r?\n/)
    .filter((line) => !line.includes(SENTINEL))
    .join("\r\n");
}

interface XtermTerminalProps {
  /** A shell name from the capability report (defaults to the host shell). */
  shell?: string;
  runtime?: string;
  /** A durable terminal id so reopening the panel reattaches to this shell. */
  owner?: string;
  /** The height class of the host box. Changing it refits the terminal. */
  heightClass?: string;
  /** Fill the parent's height instead of a fixed height (for a docked region). */
  fill?: boolean;
}

/**
 * A real interactive terminal: xterm.js rendering a live PTY-backed shell.
 *
 * Every keystroke goes straight to the PTY, so interactive programs (a REPL, a
 * prompt, Ctrl+C, arrow keys, TUI apps) work. Output streams back with low
 * latency and the window is resized to match. The session lives in the Python
 * runtime, so it survives this panel unmounting.
 */
export function XtermTerminal({ shell, runtime = "local", owner, heightClass = "h-64", fill = false }: XtermTerminalProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<import("@xterm/xterm").Terminal | null>(null);
  const sessionRef = useRef<string | null>(null);
  const cursorRef = useRef(0);
  const stopRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  // Ordered input queue: keystrokes are appended and drained by ONE in-flight
  // request at a time, so bytes reach the PTY in exactly the order typed. Sending
  // each keystroke as its own fetch let two requests race and reorder (e.g.
  // "terminal" arrived as "terimnal"); a serialized drain fixes that and coalesces
  // whatever was typed during a round-trip into the next request.
  const inputQueueRef = useRef("");
  const sendingRef = useRef(false);
  const [status, setStatus] = useState<"connecting" | "open" | "closed" | "error">("connecting");
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<{ shell: string; cwd: string; pty: boolean } | null>(null);

  const drainInput = useCallback(async () => {
    if (sendingRef.current) return;
    sendingRef.current = true;
    try {
      while (inputQueueRef.current) {
        const id = sessionRef.current;
        if (!id) break;
        const batch = inputQueueRef.current;
        inputQueueRef.current = "";
        try {
          await sendTerminalRaw(id, batch);
        } catch {
          // Re-queue on failure and stop; the next keystroke resumes the drain.
          inputQueueRef.current = batch + inputQueueRef.current;
          break;
        }
      }
    } finally {
      sendingRef.current = false;
    }
  }, []);

  const queueInput = useCallback(
    (data: string) => {
      inputQueueRef.current += data;
      void drainInput();
    },
    [drainInput],
  );

  const pump = useCallback(async () => {
    // Long-poll the runtime for new bytes and write them straight to xterm.
    while (!stopRef.current) {
      const id = sessionRef.current;
      if (!id) break;
      try {
        abortRef.current = new AbortController();
        const chunk = await streamTerminalOutput(id, cursorRef.current, 15, abortRef.current.signal);
        cursorRef.current = chunk.nextSequence;
        if (chunk.text) termRef.current?.write(stripSentinel(chunk.text));
        if (!chunk.running) {
          termRef.current?.write("\r\n\x1b[90m[session ended]\x1b[0m\r\n");
          setStatus("closed");
          break;
        }
      } catch {
        if (stopRef.current) break;
        // A transient network error: brief pause, then keep streaming.
        await new Promise((r) => setTimeout(r, 500));
      }
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    let observer: ResizeObserver | null = null;
    let onResize: (() => void) | null = null;
    let host: HTMLDivElement | null = null;
    let focusTerm: (() => void) | null = null;

    const setup = async () => {
      // Reset per-mount state. React StrictMode (dev) mounts the effect twice on
      // the SAME component instance: the first mount's cleanup sets stopRef, and
      // without this reset the second mount's stream loop would exit immediately
      // — the terminal would render but never receive a single byte.
      stopRef.current = false;
      cursorRef.current = 0;

      const [{ Terminal }, { FitAddon }] = await Promise.all([
        import("@xterm/xterm"),
        import("@xterm/addon-fit"),
      ]);
      if (disposed || !hostRef.current) return;

      const term = new Terminal({
        fontFamily: "var(--font-mono, ui-monospace, monospace)",
        fontSize: 12,
        cursorBlink: true,
        convertEol: false,
        scrollback: 5000,
        theme: {
          background: "#00000000",
          foreground: "#e4e4e7",
          cursor: "#34d399",
          selectionBackground: "#3f3f46",
        },
      });
      const fit = new FitAddon();
      term.loadAddon(fit);
      term.open(hostRef.current);
      termRef.current = term;
      try {
        fit.fit();
      } catch {
        /* the host may not be laid out yet */
      }
      // Auto-focus once the shell is open, so typing works without a click. A
      // pointerdown inside the terminal also re-focuses (xterm does this itself,
      // but an explicit handler survives a panel that stole focus first).
      host = hostRef.current;
      focusTerm = () => term.focus();
      host.addEventListener("pointerdown", focusTerm);

      // Open a persistent PTY session in the runtime.
      try {
        const session = await openTerminalSession({
          shell,
          runtime,
          owner,
          rows: term.rows,
          columns: term.cols,
        });
        if (disposed) {
          void closeTerminalSession(session.sessionId);
          return;
        }
        sessionRef.current = session.sessionId;
        setMeta({ shell: session.shell, cwd: session.cwd, pty: session.pty });
        setStatus("open");
        term.focus();
        void pump();
      } catch (err) {
        setStatus("error");
        const message = err instanceof Error ? err.message : "could not open a shell";
        setError(message);
        term.write(`\x1b[31m${message}\x1b[0m\r\n`);
      }

      // Every keystroke goes straight to the PTY — this is what makes it a real
      // terminal (interactive prompts, Ctrl+C, arrow keys, TUI programs). Queued
      // and drained in order so nothing reorders.
      term.onData(queueInput);

      onResize = () => {
        try {
          fit.fit();
        } catch {
          /* ignore */
        }
      };
      window.addEventListener("resize", onResize);
      if (typeof ResizeObserver !== "undefined" && hostRef.current) {
        observer = new ResizeObserver(onResize);
        observer.observe(hostRef.current);
      }
    };
    void setup();

    return () => {
      disposed = true;
      stopRef.current = true;
      abortRef.current?.abort();
      if (onResize) window.removeEventListener("resize", onResize);
      if (host && focusTerm) host.removeEventListener("pointerdown", focusTerm);
      observer?.disconnect();
      // The session is NOT closed on unmount: it lives in the runtime, so
      // reopening the panel (or a page reload) leaves the shell running.
      termRef.current?.dispose();
      termRef.current = null;
    };
  }, [shell, runtime, owner, pump, queueInput]);

  // When the panel changes placement, its host box resizes; the existing
  // ResizeObserver handles the refit, so nothing more is needed here. This effect
  // only nudges a refit once the layout has settled.
  useEffect(() => {
    const timer = setTimeout(() => window.dispatchEvent(new Event("resize")), 80);
    return () => clearTimeout(timer);
  }, [heightClass]);

  return (
    <div className={cn("flex flex-col", fill ? "h-full min-h-0" : "")}>
      <div className="mb-1 flex shrink-0 items-center gap-2 font-mono text-[10px] text-muted-foreground">
        <TerminalIcon size={11} />
        {status === "connecting" ? (
          <span className="flex items-center gap-1">
            <Loader2 size={10} className="animate-spin" /> opening a shell…
          </span>
        ) : status === "error" ? (
          <span className="text-rose-300">{error}</span>
        ) : (
          <>
            <span className={cn(meta?.pty ? "text-emerald-300" : "text-amber-300")}>
              {meta?.shell}
              {meta?.pty ? "" : " (no pty)"}
            </span>
            <span className="truncate">{meta?.cwd}</span>
            {status === "closed" ? <span className="text-amber-300">exited</span> : null}
          </>
        )}
      </div>
      <div
        ref={hostRef}
        className={cn(
          "w-full overflow-hidden rounded-lg bg-black/40 p-1",
          fill ? "h-full min-h-0" : heightClass,
        )}
      />
    </div>
  );
}
