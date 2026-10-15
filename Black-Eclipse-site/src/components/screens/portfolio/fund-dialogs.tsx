'use client';

// ── Fund dialogs (create / rename / add-transaction / confirm) ────────────────

import React, { useState } from 'react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { FUND_ACCENTS, FUND_ICONS, FUND_ICON_COMPONENTS } from './fund-store';
import { newTxId, type Transaction, type TxType } from '@/lib/portfolio/types';

const inputCls = 'w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl px-3 py-2.5 text-xs font-semibold focus:ring-1 focus:ring-primary outline-none';
const labelCls = 'block text-[9px] uppercase tracking-widest font-bold text-muted-foreground mb-1';

function DialogShell({ title, onClose, children, footer }: {
  title: string; onClose: () => void; children: React.ReactNode; footer: React.ReactNode;
}) {
  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-md rounded-2xl border border-white/10 glass-card-strong">
        <DialogTitle className="font-serif text-base text-foreground">{title}</DialogTitle>
        <div className="flex flex-col gap-3">{children}</div>
        <div className="mt-2 flex justify-end gap-2">{footer}</div>
      </DialogContent>
    </Dialog>
  );
}

const btnPrimary = 'rounded-xl px-4 py-2.5 text-xs font-bold border transition-all cursor-pointer bg-primary/15 text-primary border-primary/30 hover:bg-primary/25';
const btnGhost = 'rounded-xl px-4 py-2.5 text-xs font-bold border border-border/40 bg-accent/30 text-muted-foreground hover:text-primary hover:border-primary/40 transition-all cursor-pointer';

export function CreateFundDialog({ onCreate, onClose }: {
  onCreate: (name: string, icon: string, accent: string, goal: number | null, startingCash: number) => void; onClose: () => void;
}) {
  const [name, setName] = useState('');
  const [icon, setIcon] = useState(FUND_ICONS[0]);
  const [accent, setAccent] = useState(FUND_ACCENTS[0]);
  const [goal, setGoal] = useState('');
  const [startingCash, setStartingCash] = useState('');
  return (
    <DialogShell
      title="Create fund"
      onClose={onClose}
      footer={<>
        <button className={btnGhost} onClick={onClose}>Cancel</button>
        <button className={btnPrimary} disabled={!name.trim()} onClick={() => onCreate(name.trim(), icon, accent, goal ? Number(goal) : null, Number(startingCash) || 0)}>Create</button>
      </>}
    >
      <div>
        <label className={labelCls}>Fund name</label>
        <input autoFocus className={inputCls} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. College Fund" />
      </div>
      <div>
        <label className={labelCls}>Icon</label>
        <div className="grid grid-cols-4 gap-1.5">
          {FUND_ICONS.map(i => {
            const Icon = FUND_ICON_COMPONENTS[i] ?? FUND_ICON_COMPONENTS.Briefcase;
            return (
              <button key={i} onClick={() => setIcon(i)} title={i}
                className={cn('flex items-center justify-center rounded-xl border py-1.5 cursor-pointer transition-all',
                  icon === i ? 'border-primary/50 bg-primary/15 text-primary' : 'border-border/40 bg-accent/20 text-muted-foreground hover:text-foreground')}>
                <Icon size={15} />
              </button>
            );
          })}
        </div>
      </div>
      <div>
        <label className={labelCls}>Accent color</label>
        <div className="flex flex-wrap items-center gap-1.5">
          {FUND_ACCENTS.map(c => (
            <button key={c} onClick={() => setAccent(c)} style={{ background: c }}
              className={cn('h-7 w-7 rounded-full cursor-pointer transition-transform', accent === c ? 'ring-2 ring-offset-2 ring-foreground/40 scale-110' : 'opacity-70 hover:opacity-100')} />
          ))}
          <label className="ml-1 flex items-center gap-1.5 cursor-pointer">
            <input
              type="color" value={accent} onChange={e => setAccent(e.target.value)}
              className="h-7 w-7 rounded-full cursor-pointer bg-transparent border border-border/40 p-0.5"
              title="Custom color"
            />
            <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Custom</span>
          </label>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelCls}>Starting budget (cash, USD)</label>
          <input className={inputCls} value={startingCash} onChange={e => setStartingCash(e.target.value.replace(/[^\d.]/g, ''))} placeholder="0" />
        </div>
        <div>
          <label className={labelCls}>Goal value (optional, USD)</label>
          <input className={inputCls} value={goal} onChange={e => setGoal(e.target.value.replace(/[^\d]/g, ''))} placeholder="100000" />
        </div>
      </div>
      <p className="text-[10px] text-muted-foreground leading-snug">
        Starting budget is recorded as a cash deposit so P/L percentages are measured against real capital.
      </p>
    </DialogShell>
  );
}

export function RenameFundDialog({ current, onRename, onClose }: {
  current: { name: string; goalValue?: number | null }; onRename: (name: string, goal: number | null) => void; onClose: () => void;
}) {
  const [name, setName] = useState(current.name);
  const [goal, setGoal] = useState(current.goalValue != null ? String(current.goalValue) : '');
  return (
    <DialogShell
      title="Rename fund"
      onClose={onClose}
      footer={<>
        <button className={btnGhost} onClick={onClose}>Cancel</button>
        <button className={btnPrimary} disabled={!name.trim()} onClick={() => onRename(name.trim(), goal ? Number(goal) : null)}>Save</button>
      </>}
    >
      <div>
        <label className={labelCls}>Fund name</label>
        <input autoFocus className={inputCls} value={name} onChange={e => setName(e.target.value)} />
      </div>
      <div>
        <label className={labelCls}>Goal value (optional, USD)</label>
        <input className={inputCls} value={goal} onChange={e => setGoal(e.target.value.replace(/[^\d]/g, ''))} />
      </div>
    </DialogShell>
  );
}

export function AddTransactionDialog({ onAdd, onClose }: {
  onAdd: (tx: Transaction) => void; onClose: () => void;
}) {
  const [type, setType] = useState<TxType>('BUY');
  const [symbol, setSymbol] = useState('');
  const [quantity, setQuantity] = useState('');
  const [price, setPrice] = useState('');
  const [fee, setFee] = useState('');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const valid = symbol.trim() && Number(quantity) >= 0 && Number(price) >= 0;

  return (
    <DialogShell
      title="Add transaction"
      onClose={onClose}
      footer={<>
        <button className={btnGhost} onClick={onClose}>Cancel</button>
        <button className={btnPrimary} disabled={!valid} onClick={() => {
          onAdd({
            id: newTxId(), type, symbol: symbol.trim().toUpperCase(),
            quantity: Number(quantity) || 0, price: Number(price) || 0,
            fee: Number(fee) || 0, date,
          });
        }}>Add</button>
      </>}
    >
      <div>
        <label className={labelCls}>Type</label>
        <div className="flex flex-wrap gap-1.5">
          {(['BUY', 'SELL', 'DIVIDEND', 'DEPOSIT', 'WITHDRAWAL'] as TxType[]).map(t => (
            <button key={t} onClick={() => setType(t)}
              className={cn('rounded-xl border px-2.5 py-1.5 text-[10px] font-bold cursor-pointer transition-all',
                type === t ? 'border-primary/50 bg-primary/15 text-primary' : 'border-border/40 bg-accent/20 text-muted-foreground hover:text-foreground')}>
              {t}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelCls}>Symbol</label>
          <input className={inputCls} value={symbol} onChange={e => setSymbol(e.target.value)} placeholder="AAPL" />
        </div>
        <div>
          <label className={labelCls}>Date</label>
          <input type="date" className={inputCls} value={date} onChange={e => setDate(e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>Quantity</label>
          <input className={inputCls} value={quantity} onChange={e => setQuantity(e.target.value.replace(/[^\d.]/g, ''))} />
        </div>
        <div>
          <label className={labelCls}>Price</label>
          <input className={inputCls} value={price} onChange={e => setPrice(e.target.value.replace(/[^\d.]/g, ''))} />
        </div>
        <div>
          <label className={labelCls}>Fee</label>
          <input className={inputCls} value={fee} onChange={e => setFee(e.target.value.replace(/[^\d.]/g, ''))} />
        </div>
      </div>
    </DialogShell>
  );
}

export function ConfirmDialog({ title, body, confirmLabel, onConfirm, onClose }: {
  title: string; body: string; confirmLabel: string; onConfirm: () => void; onClose: () => void;
}) {
  return (
    <DialogShell
      title={title}
      onClose={onClose}
      footer={<>
        <button className={btnGhost} onClick={onClose}>Cancel</button>
        <button className="rounded-xl px-4 py-2.5 text-xs font-bold border border-rose-500/30 bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 transition-all cursor-pointer" onClick={() => { onConfirm(); onClose(); }}>
          {confirmLabel}
        </button>
      </>}
    >
      <p className="text-xs text-muted-foreground leading-relaxed">{body}</p>
    </DialogShell>
  );
}
