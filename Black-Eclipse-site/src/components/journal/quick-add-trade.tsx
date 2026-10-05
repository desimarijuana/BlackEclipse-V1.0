'use client';

// ── QuickAddTrade — one Add-Trade entry point for the whole Journal ──────────
// A glass dialog wrapping the shared `TradeForm`, mounted once in the Journal
// header so a trade can be logged from ANY tab (Overview, Calendar, Trades,
// Analytics, …) without navigating. This replaces the old behaviour where the
// only way in was the Trades/Calendar tab's local inline form.
//
// It owns the form state and the POST (the same contract as the old inline
// forms) and calls `onAdded` so the screen refreshes analytics + trades.

import React, { useState } from 'react';
import { Plus } from '@/lib/icons';
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog';
import { TradeForm, emptyTradeForm, type TradeFormState } from './trade-form';

export function QuickAddTrade({
  onAdded,
  defaultDate,
  label = 'Add Trade',
  variant = 'header',
  open: openProp,
  onOpenChange,
  trigger = true,
}: {
  onAdded: () => void;
  /** Pre-fill the entry/exit date (e.g. when opened from a calendar day). */
  defaultDate?: string;
  label?: string;
  /** `header` is the primary primary-tinted button; `inline` is a compact one. */
  variant?: 'header' | 'inline';
  /** Controlled open (optional) — lets a page open the dialog from a shortcut. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Render the built-in trigger button. Set false when the page owns the button. */
  trigger?: boolean;
}) {
  const [openState, setOpenState] = useState(false);
  const open = openProp ?? openState;
  const setOpen = (v: boolean) => {
    setOpenState(v);
    onOpenChange?.(v);
  };
  const [form, setForm] = useState<TradeFormState>(() => emptyTradeForm(defaultDate));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openDialog = () => {
    setForm(emptyTradeForm(defaultDate));
    setError(null);
    setOpen(true);
  };

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/journal/trades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: form.symbol,
          direction: form.direction,
          entry: Number(form.entry),
          exit: Number(form.exit),
          stopLoss: form.stopLoss ? Number(form.stopLoss) : null,
          takeProfit: form.takeProfit ? Number(form.takeProfit) : null,
          quantity: Number(form.quantity) || 1,
          entryTime: new Date(form.entryTime).toISOString(),
          exitTime: new Date(form.exitTime).toISOString(),
          session: form.session || null,
          timeframe: form.timeframe || null,
          emotion: form.emotion || null,
          confidence: form.confidence ? Number(form.confidence) : null,
          mistakes: form.mistakes,
          notes: form.notes || null,
          strategyId: form.strategyId || null,
          setupId: form.setupId || null,
          tagNames: form.tagNames,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to save');
      setOpen(false);
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      {trigger && (
        <button
          type="button"
          onClick={openDialog}
          className={
            variant === 'header'
              ? 'inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-3.5 py-2 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer shadow-sm shadow-primary/10'
              : 'inline-flex items-center gap-1.5 rounded-lg border border-primary/40 bg-primary/15 text-primary px-2.5 py-1.5 text-[11px] font-bold hover:bg-primary/25 transition-all cursor-pointer'
          }
        >
          <Plus size={14} /> {label}
        </button>
      )}

      <Dialog
        open={open}
        onOpenChange={(next: boolean) => {
          // Opening from outside (shortcut) must still seed a fresh form.
          if (next && !open) {
            setForm(emptyTradeForm(defaultDate));
            setError(null);
          }
          setOpen(next);
        }}
      >
        <DialogContent
          showCloseButton
          className="w-[calc(100%-2rem)] max-w-5xl sm:max-w-5xl max-h-[90dvh] overflow-y-auto scrollbar-hide rounded-2xl border border-white/10 glass-card-strong text-foreground p-0"
        >
          <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-border/10 px-5 py-3.5 glass-card-strong">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/15">
                <Plus className="text-primary" size={16} />
              </span>
              <DialogTitle className="font-serif text-base font-semibold tracking-tight text-foreground">
                Add Trade
              </DialogTitle>
            </div>
          </div>
          <div className="p-5">
            <TradeForm
              form={form}
              onChange={(patch) => setForm((f) => ({ ...f, ...patch }))}
              onSubmit={submit}
              onCancel={() => setOpen(false)}
              saving={saving}
              error={error}
            />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
