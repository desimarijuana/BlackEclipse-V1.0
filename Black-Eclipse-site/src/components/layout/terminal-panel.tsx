'use client';

import { useEffect, useRef, useState } from 'react';
import { Activity, Network, Terminal as TerminalIcon, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ProcessPanel } from '@/components/terminal/process-panel';
import { PortPanel } from '@/components/terminal/port-panel';
import { executeTerminalCommand } from '@/lib/harness/terminal-browser';

interface Line {
  kind: 'input' | 'stdout' | 'stderr' | 'meta';
  text: string;
}

type View = 'terminal' | 'processes' | 'ports';

// A visible terminal panel, toggled with Ctrl/Cmd + ` (backquote).
// Commands run through the runtime's /code/shell endpoint (host shell,
// confined to the server-resolved workspace root). The Processes and Ports
// views read the SAME backend the agent's terminal tools use.
export function TerminalPanel() {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>('terminal');
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
      // The SAME backend the agent's terminal tools use (one execution path).
      const r = await executeTerminalCommand(command);
      if (r.stdout) setLines((prev) => [...prev, { kind: 'stdout', text: r.stdout.replace(/\n$/, '') }]);
      if (r.stderr) setLines((prev) => [...prev, { kind: 'stderr', text: r.stderr.replace(/\n$/, '') }]);
      if (r.error) {
        const { category, message } = r.error;
        setLines((prev) => [...prev, { kind: 'stderr', text: `[${category}] ${message}` }]);
      }
      setLines((prev) => [
        ...prev,
        { kind: 'meta', text: `exit=${r.exitCode} ${r.durationMs}ms${r.timedOut ? ' TIMED OUT' : ''}` },
      ]);
    } catch (err) {
      setLines((prev) => [...prev, { kind: 'meta', text: err instanceof Error ? err.message : 'request failed' }]);
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  const tabs: Array<{ id: View; label: string; icon: typeof TerminalIcon }> = [
    { id: 'terminal', label: 'Terminal', icon: TerminalIcon },
    { id: 'processes', label: 'Processes', icon: Activity },
    { id: 'ports', label: 'Ports', icon: Network },
  ];

  return (
    <div className="fixed inset-x-4 bottom-4 z-[80] glass-card-strong rounded-2xl border border-white/10 p-3 shadow-2xl">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setView(tab.id)}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs transition',
                view === tab.id ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <tab.icon size={13} /> {tab.label}
            </button>
          ))}
          <span className="ml-2 text-[10px] text-muted-foreground">Ctrl/Cmd + ` to toggle</span>
        </div>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close terminal" className="text-muted-foreground hover:text-foreground">
          <X size={14} />
        </button>
      </div>

      {view === 'processes' ? (
        <div className="h-64 rounded-lg bg-black/40 p-2">
          <ProcessPanel />
        </div>
      ) : view === 'ports' ? (
        <div className="h-64 rounded-lg bg-black/40 p-2">
          <PortPanel />
        </div>
      ) : (
        <>
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
        </>
      )}
    </div>
  );
}
