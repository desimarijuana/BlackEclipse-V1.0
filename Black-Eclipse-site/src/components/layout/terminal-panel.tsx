'use client';

import { useEffect, useRef, useState } from 'react';
import { Terminal as TerminalIcon, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Line {
  kind: 'input' | 'stdout' | 'stderr' | 'meta';
  text: string;
}

// A visible terminal panel, toggled with Ctrl/Cmd + ` (backquote).
// Commands run through the runtime's /code/shell endpoint (host shell,
// confined to the server-resolved workspace root).
export function TerminalPanel() {
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === '`') {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [lines, open]);

  const run = async () => {
    const command = input.trim();
    if (!command || busy) return;
    setLines((prev) => [...prev, { kind: 'input', text: `$ ${command}` }]);
    setHistory((prev) => [...prev, command]);
    setHistoryIndex(-1);
    setInput('');
    setBusy(true);
    try {
      const res = await fetch('/api/code/shell', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command }),
      });
      const body = await res.json();
      if (!res.ok) {
        setLines((prev) => [...prev, { kind: 'meta', text: body.error ?? `HTTP ${res.status}` }]);
      } else {
        const r = body.result;
        if (r.stdout) setLines((prev) => [...prev, { kind: 'stdout', text: r.stdout.replace(/\n$/, '') }]);
        if (r.stderr) setLines((prev) => [...prev, { kind: 'stderr', text: r.stderr.replace(/\n$/, '') }]);
        setLines((prev) => [
          ...prev,
          { kind: 'meta', text: `exit=${r.exitCode} ${r.durationMs}ms${r.timedOut ? ' TIMED OUT' : ''}` },
        ]);
      }
    } catch (err) {
      setLines((prev) => [...prev, { kind: 'meta', text: err instanceof Error ? err.message : 'request failed' }]);
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-x-4 bottom-4 z-[80] glass-card-strong rounded-2xl border border-white/10 p-3 shadow-2xl">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <TerminalIcon size={14} /> Eclipse Terminal — Ctrl/Cmd + ` to toggle
        </div>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close terminal" className="text-muted-foreground hover:text-foreground">
          <X size={14} />
        </button>
      </div>
      <div ref={scrollRef} className="max-h-64 overflow-y-auto rounded-lg bg-black/40 p-2 font-mono text-[12px] leading-5">
        {lines.length === 0 ? (
          <div className="text-muted-foreground">Type a command and press Enter.</div>
        ) : (
          lines.map((line, i) => (
            <pre
              key={i}
              className={cn(
                'whitespace-pre-wrap break-words',
                line.kind === 'input' && 'text-emerald-300',
                line.kind === 'stderr' && 'text-rose-300',
                line.kind === 'meta' && 'text-amber-300/80',
                line.kind === 'stdout' && 'text-zinc-200',
              )}
            >
              {line.text}
            </pre>
          ))
        )}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <span className="font-mono text-[12px] text-emerald-300">$</span>
        <input
          autoFocus
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void run();
            else if (e.key === 'ArrowUp') {
              setHistoryIndex((i) => {
                const next = i === -1 ? history.length - 1 : Math.max(0, i - 1);
                if (history[next] !== undefined) setInput(history[next]);
                return next;
              });
            } else if (e.key === 'ArrowDown') {
              setHistoryIndex((i) => {
                if (i === -1) return -1;
                const next = i + 1;
                if (next >= history.length) {
                  setInput('');
                  return -1;
                }
                setInput(history[next]);
                return next;
              });
            }
          }}
          placeholder={busy ? 'running…' : 'command'}
          className="flex-1 bg-transparent font-mono text-[12px] text-foreground outline-none placeholder:text-muted-foreground"
        />
      </div>
    </div>
  );
}
