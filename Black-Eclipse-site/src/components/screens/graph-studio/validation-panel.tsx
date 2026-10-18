'use client';

import { AlertTriangle, CheckCircle2, WarningCircle } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';

// Lists the live validation diagnostics. Clicking one selects the offending
// node so the canvas highlights it.

export function ValidationPanel() {
  const diagnostics = useGraphEditor((s) => s.diagnostics);
  const setSelection = useGraphEditor((s) => s.setSelection);

  const errors = diagnostics.filter((d) => d.severity === 'error').length;
  const warnings = diagnostics.filter((d) => d.severity === 'warning').length;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2 text-[11px]">
        {errors === 0 && warnings === 0 ? (
          <span className="flex items-center gap-1.5 text-emerald-400">
            <CheckCircle2 size={13} /> No issues
          </span>
        ) : (
          <>
            {errors > 0 && (
              <span className="flex items-center gap-1.5 text-rose-400">
                <WarningCircle size={13} /> {errors} error{errors === 1 ? '' : 's'}
              </span>
            )}
            {warnings > 0 && (
              <span className="flex items-center gap-1.5 text-amber-400">
                <AlertTriangle size={13} /> {warnings} warning{warnings === 1 ? '' : 's'}
              </span>
            )}
          </>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {diagnostics.length === 0 && (
          <p className="px-1 py-3 text-[11px] text-muted-foreground">This graph is structurally valid.</p>
        )}
        <ul className="space-y-1">
          {diagnostics.map((d, i) => (
            <li key={`${d.code}-${d.nodeId ?? d.edgeId ?? i}`}>
              <button
                type="button"
                onClick={() => d.nodeId && setSelection({ nodeIds: [d.nodeId], edgeIds: [] })}
                className={cn(
                  'flex w-full items-start gap-1.5 rounded-md border px-2 py-1.5 text-left text-[11px] leading-snug',
                  d.severity === 'error'
                    ? 'border-rose-500/25 bg-rose-500/5 text-rose-200'
                    : 'border-amber-500/20 bg-amber-500/5 text-amber-200',
                )}
              >
                <span className="mt-0.5 shrink-0">
                  {d.severity === 'error' ? <WarningCircle size={12} /> : <AlertTriangle size={12} />}
                </span>
                <span className="min-w-0 flex-1">{d.message}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
