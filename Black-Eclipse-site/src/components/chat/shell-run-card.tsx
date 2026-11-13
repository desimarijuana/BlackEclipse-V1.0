'use client';

import { Check, Copy, Terminal } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { shellExitLabel, shellOutput, shellSucceeded } from '@/lib/chat/shell';
import type { ShellRun } from '@/types/chat';

/**
 * A `!` shell run as it appears in the transcript: the command, where it ran,
 * how long it took, and its real output. Rendered INSIDE the user turn so the
 * run stays part of the conversation the agent reads next — never a detached
 * log that scrolls away.
 *
 * Honesty rules: the exit badge reports the runtime's actual code, a runtime
 * that could not start the command says so, and truncated output says so.
 */
export function ShellRunCard({ run, copied, onCopy }: {
  run: ShellRun;
  copied?: boolean;
  onCopy?: () => void;
}) {
  const output = shellOutput(run);
  const ok = shellSucceeded(run);
  const failed = !run.error && !run.timedOut && run.exitCode !== null && run.exitCode !== 0;

  return (
    <div className="mb-1.5 w-full min-w-[min(100%,22rem)] overflow-hidden rounded-xl border border-border/40 glass-card-subtle">
      <div className="flex items-center gap-1.5 border-b border-border/30 px-2 py-1.5">
        <span className="flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground/70">
          <Terminal size={11} />
        </span>
        <code className="min-w-0 flex-1 truncate font-mono text-[11px] text-foreground/90">
          <span className="select-none text-muted-foreground/50">$ </span>
          {run.command}
        </code>
        <span
          className={cn(
            'shrink-0 rounded-full border px-1.5 py-px font-mono text-[9px] font-medium',
            ok && 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300/90',
            failed && 'border-rose-500/30 bg-rose-500/10 text-rose-300/90',
            !ok && !failed && 'border-amber-500/30 bg-amber-500/10 text-amber-300/90',
          )}
          title={`Exit status: ${shellExitLabel(run)}`}
        >
          {shellExitLabel(run)}
        </span>
        {onCopy && (
          <button
            type="button"
            onClick={onCopy}
            title={copied ? 'Copied output' : 'Copy output'}
            aria-label="Copy shell output"
            className="shrink-0 rounded-full p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {copied ? <Check size={10} /> : <Copy size={10} />}
          </button>
        )}
      </div>

      {run.error ? (
        <p className="px-2.5 py-2 text-[10.5px] leading-snug text-muted-foreground/80">
          {run.error}
        </p>
      ) : (
        <pre className="chat-composer-scroll max-h-56 overflow-auto whitespace-pre-wrap break-words px-2.5 py-2 font-mono text-[10.5px] leading-relaxed text-foreground/85">
          {output || '(no output)'}
        </pre>
      )}

      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 border-t border-border/25 px-2 py-1 font-mono text-[9px] text-muted-foreground/60">
        {run.cwd && <span className="truncate">{run.cwd}</span>}
        {!run.error && <span>{run.durationMs}ms</span>}
        {run.truncated && <span className="text-amber-300/80">truncated</span>}
        {run.timedOut && <span className="text-amber-300/80">timed out</span>}
      </div>
    </div>
  );
}
