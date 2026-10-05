'use client';

// ── The chat capability panel (Phase 14) ─────────────────────────────────────
// Renders, for a chat turn that used the code capability: what Eclipse set out to
// do (the profile, in plain words), the proof it ran (the existing Phase-4
// CodeVerificationPanel, composed — never re-rendered), and the raw refusal code
// behind a "details" affordance.
//
// The classifier's verdict is NEVER shown as a category: the user sees what
// Eclipse will do ("I'll look at the project, make the change in a copy, and run
// the checks"), not "intent classified as code". Every string is an i18n key under
// `code.chat.*` so the plain-language gate can scan it.

import { useState } from 'react';
import { Hammer, Search } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import { coerceChatCapability, headlineKey } from '@/lib/harness/chat-capability-view';
import { CodeVerificationPanel } from './code-verification-panel';

export interface ChatCapabilityPanelProps {
  /** The narrow profile the turn was bound to, when it was a coding request. */
  autonomy?: string | null;
  /** The run's Phase-4 verification ledger, when the turn used code. */
  verification?: unknown;
  /** Phase 14 §6.4: the runtime-derived view; when present it wins. */
  capability?: unknown;
  compact?: boolean;
}

export function ChatCapabilityPanel({ autonomy, verification, capability, compact = false }: ChatCapabilityPanelProps) {
  const t = useT();
  const [open, setOpen] = useState(false);
  // Prefer the runtime-derived view; fall back to the flat fields (an older row
  // that persisted only the verification blob).
  const view = coerceChatCapability(capability);
  const effectiveAutonomy = view?.profile ?? autonomy;
  const effectiveVerification = view?.verification ?? verification;
  const key = view?.headline ?? headlineKey(effectiveAutonomy);

  // An ordinary turn with no code profile and no verification renders nothing.
  if (!key && !effectiveVerification) return null;

  const editVerify = effectiveAutonomy === 'edit_verify';

  return (
    <div className={cn('mt-2 w-full', compact ? 'text-[11px]' : 'text-[12px]')}>
      {key && (
        <div className="glass-card-subtle flex items-center gap-2 rounded-xl border border-border/40 px-3 py-2">
          {editVerify
            ? <Hammer size={13} className="shrink-0 text-primary" />
            : <Search size={13} className="shrink-0 text-primary" />}
          <span className="min-w-0 flex-1 text-muted-foreground">{t(key)}</span>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="shrink-0 text-[11px] text-muted-foreground/70 underline-offset-2 hover:underline"
            aria-expanded={open}
          >
            {t('code.chat.details')}
          </button>
        </div>
      )}

      {/* The proof it ran — the existing panel, composed. */}
      <CodeVerificationPanel verification={effectiveVerification} compact={compact} />

      {open && key && (
        <dl className="mt-1 space-y-0.5 pl-3 font-mono text-[10.5px] text-muted-foreground/70">
          <div className="flex gap-2">
            <dt className="text-muted-foreground/50">{t('code.chat.detail.profile')}</dt>
            <dd>{effectiveAutonomy}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}
