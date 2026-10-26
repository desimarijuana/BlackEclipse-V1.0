'use client';

// ── Operator-run authorization ───────────────────────────────────────────────
// An explicit dialog is the UI half of the operator envelope. It lists exactly
// what this graph asks for; the runtime still derives the grants itself and
// refuses anything not listed here. Live trading and external writes are never
// offered.

import { createPortal } from 'react-dom';
import { ShieldPlus, X } from '@/lib/icons';

export interface OperatorRunNeeds {
  requiresNetwork: boolean;
  networkNodes: string[];
  tradingNodes: string[];
  writeNodes: string[];
  writeNodeTypes: string[];
}

export function RunAuthorizationDialog({
  needs, onCancel, onConfirm,
}: {
  needs: OperatorRunNeeds;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return createPortal(
    <div className="fixed inset-0 z-[125] flex items-center justify-center px-4">
      <button type="button" aria-label="Cancel" onClick={onCancel} className="absolute inset-0 cursor-default bg-black/50" />
      <div className="glass-card-strong relative w-full max-w-md rounded-2xl border border-white/10 p-4 shadow-2xl">
        <div className="flex items-start gap-2.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 text-amber-300">
            <ShieldPlus size={17} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-[14px] font-semibold text-foreground">Authorize operator run</h2>
            <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
              This graph asks to act beyond a test run. Only the capabilities declared by its nodes are granted.
            </p>
          </div>
          <button type="button" onClick={onCancel} className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground">
            <X size={13} />
          </button>
        </div>

        <ul className="mt-3 space-y-2">
          {needs.requiresNetwork && (
            <li className="rounded-lg border border-sky-500/25 bg-sky-500/5 px-2.5 py-2">
              <div className="text-[11px] font-medium text-sky-200">Network access</div>
              <p className="mt-0.5 text-[10.5px] text-muted-foreground">{needs.networkNodes.join(', ')}</p>
            </li>
          )}
          {needs.tradingNodes.length > 0 && (
            <li className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-2.5 py-2">
              <div className="text-[11px] font-medium text-amber-200">Paper trading only</div>
              <p className="mt-0.5 text-[10.5px] text-muted-foreground">
                {needs.tradingNodes.join(', ')} — simulated fills; no broker is contacted and live trading is never granted.
              </p>
            </li>
          )}
          {needs.writeNodes.length > 0 && (
            <li className="rounded-lg border border-white/10 bg-white/[0.02] px-2.5 py-2">
              <div className="text-[11px] font-medium text-foreground">Local render</div>
              <p className="mt-0.5 text-[10.5px] text-muted-foreground">
                {needs.writeNodes.join(', ')} — writes project files and an artifact; no external write.
              </p>
            </li>
          )}
        </ul>

        <div className="mt-4 flex items-center justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-lg border border-white/10 px-3 py-1.5 text-[11px] text-muted-foreground hover:bg-white/5 hover:text-foreground">
            Cancel
          </button>
          <button type="button" onClick={onConfirm} className="rounded-lg border border-amber-400/40 bg-amber-500/15 px-3 py-1.5 text-[11px] font-medium text-amber-200 hover:bg-amber-500/25">
            Authorize run
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
