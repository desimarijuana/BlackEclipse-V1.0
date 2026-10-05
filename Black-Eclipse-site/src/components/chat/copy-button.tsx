'use client';

// ── CopyButton — one small clipboard affordance for markdown blocks ─────────
// Used by the code-block and table renderers. Shows a transient "Copied" state
// and never throws when the clipboard is unavailable (e.g. insecure context).

import { useCallback, useRef, useState } from 'react';
import { Check, Copy } from '@/lib/icons';
import { cn } from '@/lib/utils';

export interface CopyButtonProps {
  /** The exact text to place on the clipboard. */
  value: string;
  /** Accessible label / tooltip noun, e.g. "code" or "table". */
  label?: string;
  className?: string;
}

export function CopyButton({ value, label = 'content', className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      return;
    }
    setCopied(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopied(false), 1500);
  }, [value]);

  return (
    <button
      type="button"
      onClick={() => void copy()}
      title={copied ? 'Copied' : `Copy ${label}`}
      aria-label={copied ? 'Copied' : `Copy ${label}`}
      className={cn(
        'inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer',
        className,
      )}
    >
      {copied ? <Check size={11} /> : <Copy size={11} />}
      <span>{copied ? 'Copied' : 'Copy'}</span>
    </button>
  );
}
