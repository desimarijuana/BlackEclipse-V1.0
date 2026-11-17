'use client';

// ── JournalSettings — profile settings + trading-account management ──────────
// A glass dialog reachable from the Journal header. Two concerns:
//  1. Trader settings (name, currency, account size, risk-per-trade) — these
//     drive currency equity and the discipline risk rule.
//  2. Trading accounts (multi-account support) — every trade can be tagged to
//     one; the account switcher/currency equity reads from here.

import React, { useCallback, useEffect, useState } from 'react';
import { confirmDialog } from '@/lib/ui/confirm-dialog';
import { Settings, Plus, Trash2, Check } from '@/lib/icons';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { BrokerSyncSettings } from './broker-sync-settings';

interface Account { id: string; name: string; broker: string | null; currency: string; initialBalance: number; archived: boolean }
interface Profile { name: string; currency: string; accountSize: number; riskPerTrade: number }

export function JournalSettings({ onChanged }: { onChanged?: () => void }) {
  const [open, setOpen] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savedProfile, setSavedProfile] = useState(false);

  const [newAccount, setNewAccount] = useState({ name: '', broker: '', currency: 'USD', initialBalance: '' });

  const load = useCallback(async () => {
    const [pRes, aRes] = await Promise.all([
      fetch('/api/journal/profile'),
      fetch('/api/journal/accounts'),
    ]);
    const pData = await pRes.json();
    const aData = await aRes.json();
    setProfile(pData.profile ?? null);
    setAccounts(aData.accounts ?? []);
  }, []);

  useEffect(() => { if (open) void load(); }, [open, load]);

  const saveProfile = async () => {
    if (!profile) return;
    setSavingProfile(true);
    setSavedProfile(false);
    try {
      await fetch('/api/journal/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profile),
      });
      setSavedProfile(true);
      onChanged?.();
    } finally {
      setSavingProfile(false);
    }
  };

  const addAccount = async () => {
    if (!newAccount.name.trim()) return;
    await fetch('/api/journal/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newAccount.name,
        broker: newAccount.broker || null,
        currency: newAccount.currency || 'USD',
        initialBalance: Number(newAccount.initialBalance) || 0,
      }),
    });
    setNewAccount({ name: '', broker: '', currency: 'USD', initialBalance: '' });
    await load();
    onChanged?.();
  };

  const removeAccount = async (id: string) => {
    if (!(await confirmDialog({ title: 'Delete this account?', description: 'Trades assigned to it will keep their history.', tone: 'danger' }))) return;
    await fetch(`/api/journal/accounts/${id}`, { method: 'DELETE' });
    await load();
    onChanged?.();
  };

  const inputCls = 'w-full rounded-lg bg-background/60 border border-border/40 hover:border-primary/50 px-3 py-2 text-xs font-mono focus:ring-1 focus:ring-primary outline-none transition-colors';

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground transition-all cursor-pointer"
        title="Journal settings"
      >
        <Settings size={14} /> Settings
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          showCloseButton
          className="w-[calc(100%-2rem)] max-w-3xl max-h-[90dvh] overflow-y-auto scrollbar-hide rounded-2xl border border-white/10 glass-card-strong text-foreground p-0"
        >
          <div className="sticky top-0 z-10 flex items-center gap-2.5 border-b border-border/10 px-5 py-3.5 glass-card-strong">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/15">
              <Settings className="text-primary" size={16} />
            </span>
            <DialogTitle className="font-serif text-base font-semibold tracking-tight text-foreground">
              Journal Settings
            </DialogTitle>
          </div>

          <div className="flex flex-col gap-6 p-5">
            {/* Profile */}
            <section>
              <h3 className="mb-3 text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Trader</h3>
              {profile ? (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <label className="flex flex-col gap-1">
                    <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">Name</span>
                    <input value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} className={inputCls} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">Currency</span>
                    <input value={profile.currency} onChange={(e) => setProfile({ ...profile, currency: e.target.value.toUpperCase() })} className={inputCls} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">Account Size</span>
                    <input type="number" step="any" value={profile.accountSize} onChange={(e) => setProfile({ ...profile, accountSize: Number(e.target.value) })} className={inputCls} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">Risk / Trade</span>
                    <div className="flex items-center gap-2">
                      <input type="number" step="0.1" min={0} value={(profile.riskPerTrade * 100).toFixed(2)} onChange={(e) => setProfile({ ...profile, riskPerTrade: Number(e.target.value) / 100 })} className={inputCls} />
                      <span className="text-xs text-muted-foreground">%</span>
                    </div>
                  </label>
                  <div className="col-span-full flex items-center gap-3">
                    <button onClick={() => void saveProfile()} disabled={savingProfile} className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-4 py-2 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50">
                      {savingProfile ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary/30 border-t-primary" /> : <Check size={13} />} Save
                    </button>
                    {savedProfile && <span className="text-[11px] text-emerald-400 font-semibold">Saved</span>}
                    <span className="ml-auto text-[10px] text-muted-foreground">Drives currency equity &amp; the discipline risk rule.</span>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground italic">Loading…</p>
              )}
            </section>

            {/* Accounts */}
            <section>
              <h3 className="mb-3 text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Trading Accounts</h3>
              <div className="flex flex-col gap-2">
                {accounts.map((a) => (
                  <div key={a.id} className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-foreground truncate">{a.name}{a.broker ? <span className="text-muted-foreground font-normal"> · {a.broker}</span> : null}</p>
                      <p className="font-mono text-[10px] text-muted-foreground">{a.currency} · start {a.initialBalance.toLocaleString()}</p>
                    </div>
                    <button onClick={() => void removeAccount(a.id)} className="text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer" title="Delete account">
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
                {accounts.length === 0 && <p className="text-[11px] text-muted-foreground/60 italic">No accounts yet. Add one to separate P&amp;L by broker/account.</p>}
              </div>

              <div className={cn('mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5')}>
                <input value={newAccount.name} onChange={(e) => setNewAccount({ ...newAccount, name: e.target.value })} placeholder="Name" className={cn(inputCls, 'col-span-2 sm:col-span-1')} />
                <input value={newAccount.broker} onChange={(e) => setNewAccount({ ...newAccount, broker: e.target.value })} placeholder="Broker" className={inputCls} />
                <input value={newAccount.currency} onChange={(e) => setNewAccount({ ...newAccount, currency: e.target.value.toUpperCase() })} placeholder="USD" className={inputCls} />
                <input type="number" step="any" value={newAccount.initialBalance} onChange={(e) => setNewAccount({ ...newAccount, initialBalance: e.target.value })} placeholder="Balance" className={inputCls} />
                <button onClick={() => void addAccount()} className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-3 py-2 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer">
                  <Plus size={13} /> Add
                </button>
              </div>
            </section>

            {/* Broker sync */}
            <section>
              <h3 className="mb-1 text-[10px] uppercase tracking-widest font-bold text-muted-foreground">
                Broker Connection
              </h3>
              <p className="mb-3 text-[10px] text-muted-foreground/70">
                Project reconciled broker trades into this journal. The broker stays the source
                of truth; notes and reviews you write here are never overwritten.
              </p>
              <BrokerSyncSettings accounts={accounts.map((a) => ({ id: a.id, name: a.name }))} />
            </section>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
