'use client';

// ── Eclipse SDK — the user control surface ───────────────────────────────────
// One screen that exercises the SAME typed SDK a user (or a script) imports:
// create declarative widgets, compose pages, create fund portfolios, add stock,
// change the app design and put passphrase locks on any resource. It is a thin
// client over `/api/sdk/**` — no second implementation of any capability.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { Lock, Palette, Plus, RefreshCw, Trash2, WandSparkles } from '@/lib/icons';
import {
  eclipseSdk,
  SdkError,
  type SdkCapabilities,
  type SdkFund,
  type SdkLock,
  type SdkWidgetPrimitive,
  type SdkWidgetRecord,
  type ThemePatch,
} from '@/lib/sdk';
import { refreshSdkWidgets, useSdkWidgets } from '@/lib/sdk/widgets';
import { useThemeStore } from '@/lib/theme';

const PRIMITIVES: SdkWidgetPrimitive[] = [
  'data-table', 'metric-card', 'line-chart', 'area-chart', 'bar-chart',
  'pie-chart', 'list', 'markdown', 'status-indicator', 'empty-state', 'error-state',
];

const SOURCE_PRIMITIVES = new Set<SdkWidgetPrimitive>([
  'data-table', 'metric-card', 'line-chart', 'area-chart', 'bar-chart', 'pie-chart', 'list',
]);

const LOCK_RESOURCES: SdkLock['resourceType'][] = ['page', 'widget', 'portfolio', 'design'];

function slugify(value: string): string {
  return value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'widget';
}

function errorMessage(err: unknown): string {
  if (err instanceof SdkError) {
    return `${err.message}${err.hint ? ` — hint: ${err.hint}` : ''}`;
  }
  return err instanceof Error ? err.message : 'request failed';
}

// ── small primitives ─────────────────────────────────────────────────────────

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
      <span className="font-medium text-foreground/80">{label}</span>
      {children}
      {hint && <span className="text-[10px] text-muted-foreground/70">{hint}</span>}
    </label>
  );
}

const inputClass = 'w-full rounded-lg border border-border/40 bg-black/20 px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-primary/50';

function Section({ title, icon: Icon, children, action }: {
  title: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section className="glass-card flex min-h-0 flex-col rounded-xl p-4">
      <header className="mb-3 flex items-center justify-between gap-2 border-b border-border/10 pb-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Icon size={14} className="text-primary" /> {title}
        </h2>
        {action}
      </header>
      {children}
    </section>
  );
}

// ── widgets ──────────────────────────────────────────────────────────────────

function WidgetSection({ onChanged }: { onChanged: () => void }) {
  const stored = useSdkWidgets();
  const [label, setLabel] = useState('Portfolio value');
  const [primitive, setPrimitive] = useState<SdkWidgetPrimitive>('metric-card');
  const [source, setSource] = useState('portfolio:pf_REPLACE:summary.totalValue');
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true);
    try {
      await eclipseSdk.widgets.create({
        slug: slugify(label),
        label,
        primitive,
        source: SOURCE_PRIMITIVES.has(primitive) ? source : undefined,
        config: primitive === 'markdown' ? { text: '## Notes\nEdit this widget config.' } : {},
      });
      await refreshSdkWidgets();
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const remove = async (record: SdkWidgetRecord) => {
    await eclipseSdk.widgets.remove(record.componentId);
    await refreshSdkWidgets();
    onChanged();
  };

  return (
    <Section title="Widgets" icon={WandSparkles} action={<span className="text-[10px] text-muted-foreground">{stored.length} user widgets</span>}>
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Name">
          <input className={inputClass} value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
        <Field label="Primitive">
          <select className={inputClass} value={primitive} onChange={(e) => setPrimitive(e.target.value as SdkWidgetPrimitive)}>
            {PRIMITIVES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
        {SOURCE_PRIMITIVES.has(primitive) && (
          <Field label="Data source" hint="Allow-listed source, e.g. portfolio:<id>:positions" >
            <input className={inputClass} value={source} onChange={(e) => setSource(e.target.value)} />
          </Field>
        )}
        <div className="flex items-end">
          <button type="button" onClick={() => void create()} disabled={busy} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs disabled:opacity-50">
            <Plus size={13} /> Create widget
          </button>
        </div>
      </div>
      <div className="mt-3 max-h-40 space-y-1 overflow-y-auto">
        {stored.length === 0 && <p className="text-[11px] italic text-muted-foreground/70">No user widgets yet.</p>}
        {stored.map((widget) => (
          <div key={widget.componentId} className="flex items-center justify-between gap-2 rounded-lg border border-border/20 px-2 py-1.5">
            <div className="min-w-0">
              <p className="truncate text-xs text-foreground">{widget.label}</p>
              <p className="truncate font-mono text-[9px] text-muted-foreground/60">{widget.componentId} · {widget.primitive}</p>
            </div>
            <button type="button" onClick={() => void remove(widget)} title="Delete widget" className="rounded p-1 text-muted-foreground hover:text-rose-300">
              <Trash2 size={12} />
            </button>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ── pages ────────────────────────────────────────────────────────────────────

function PageSection({ onChanged }: { onChanged: () => void }) {
  const [title, setTitle] = useState('My SDK page');
  const [path, setPath] = useState('');
  const [components, setComponents] = useState('metric-card');
  const [pages, setPages] = useState<{ id: string; title: string; path?: string | null }[]>([]);

  const refresh = useCallback(async () => {
    try {
      const { blueprints } = await eclipseSdk.pages.list();
      setPages(blueprints);
    } catch {
      setPages([]);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const create = async () => {
    const widgets = components.split(',').map((id) => id.trim()).filter(Boolean).map((componentId) => ({ componentId }));
    await eclipseSdk.pages.create({
      title,
      path: path.trim() || undefined,
      widgets,
    });
    await refresh();
    onChanged();
  };

  return (
    <Section title="Pages" icon={Plus} action={<span className="text-[10px] text-muted-foreground">{pages.length} pages</span>}>
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Title"><input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="Path" hint="Optional. Enables ?tab=pages&page=<path>">
          <input className={inputClass} value={path} onChange={(e) => setPath(e.target.value)} placeholder="/desk/rates" />
        </Field>
        <Field label="Widgets" hint="Comma-separated component ids (e.g. metric-card, sdk.my-widget)">
          <input className={inputClass} value={components} onChange={(e) => setComponents(e.target.value)} />
        </Field>
        <div className="flex items-end">
          <button type="button" onClick={() => void create()} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs">
            <Plus size={13} /> Create page
          </button>
        </div>
      </div>
      <div className="mt-3 max-h-40 space-y-1 overflow-y-auto">
        {pages.map((page) => (
          <div key={page.id} className="flex items-center justify-between gap-2 rounded-lg border border-border/20 px-2 py-1.5">
            <button type="button" onClick={() => eclipseSdk.pages.open(page.id)} className="min-w-0 flex-1 text-left">
              <p className="truncate text-xs text-foreground hover:text-primary">{page.title}</p>
              <p className="truncate font-mono text-[9px] text-muted-foreground/60">{page.path || page.id}</p>
            </button>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ── portfolio / funds ────────────────────────────────────────────────────────

function PortfolioSection({ onChanged }: { onChanged: () => void }) {
  const [funds, setFunds] = useState<SdkFund[]>([]);
  const [name, setName] = useState('Growth Fund');
  const [goal, setGoal] = useState('Long-term capital growth');
  const [selected, setSelected] = useState('');
  const [symbol, setSymbol] = useState('AAPL');
  const [quantity, setQuantity] = useState('10');
  const [price, setPrice] = useState('180');
  const [note, setNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const { portfolios } = await eclipseSdk.portfolio.list();
      setFunds(portfolios);
      setSelected((current) => current || portfolios[0]?.id || '');
    } catch {
      setFunds([]);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const createFund = async () => {
    await eclipseSdk.portfolio.createFund({ name, goal, baseCurrency: 'USD' });
    await refresh();
    onChanged();
  };

  const addStock = async () => {
    if (!selected) return;
    const result = await eclipseSdk.portfolio.addStock(selected, {
      symbol, quantity, price: price || undefined,
    });
    setNote(result.status === 'SUCCESS' ? `Added ${quantity} ${symbol}` : `Status: ${result.status}`);
    await refresh();
    onChanged();
  };

  return (
    <Section title="Fund portfolios" icon={Palette} action={<span className="text-[10px] text-muted-foreground">{funds.length} portfolios</span>}>
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Fund name"><input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Goal"><input className={inputClass} value={goal} onChange={(e) => setGoal(e.target.value)} /></Field>
        <div className="flex items-end">
          <button type="button" onClick={() => void createFund()} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs">
            <Plus size={13} /> Create fund
          </button>
        </div>
      </div>
      <div className="mt-3 border-t border-border/10 pt-2">
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Portfolio">
            <select className={inputClass} value={selected} onChange={(e) => setSelected(e.target.value)}>
              {funds.map((fund) => <option key={fund.id} value={fund.id}>{fund.name} ({fund.kind})</option>)}
            </select>
          </Field>
          <Field label="Symbol"><input className={cn(inputClass, 'w-24')} value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} /></Field>
          <Field label="Quantity"><input className={cn(inputClass, 'w-24')} value={quantity} onChange={(e) => setQuantity(e.target.value)} /></Field>
          <Field label="Price"><input className={cn(inputClass, 'w-24')} value={price} onChange={(e) => setPrice(e.target.value)} /></Field>
          <button type="button" onClick={() => void addStock()} disabled={!selected} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs disabled:opacity-50">
            <Plus size={13} /> Add stock
          </button>
        </div>
        {note && <p className="mt-1.5 text-[10px] text-emerald-300">{note}</p>}
        <div className="mt-2 max-h-28 space-y-1 overflow-y-auto">
          {funds.map((fund) => (
            <div key={fund.id} className="flex items-center justify-between gap-2 rounded-lg border border-border/20 px-2 py-1">
              <span className="truncate text-[11px] text-foreground">{fund.name}</span>
              <span className="rounded border border-primary/25 bg-primary/10 px-1 py-0.5 font-mono text-[8px] uppercase text-primary">{fund.kind}</span>
            </div>
          ))}
        </div>
      </div>
    </Section>
  );
}

// ── design ───────────────────────────────────────────────────────────────────

function DesignSection({ caps }: { caps: SdkCapabilities | null }) {
  const [primary, setPrimary] = useState('#7aff78');
  const [presetId, setPresetId] = useState('');
  const [note, setNote] = useState<string | null>(null);
  const presets = caps?.design.presets ?? [];

  useEffect(() => {
    try {
      void eclipseSdk.design.get().then(({ theme }) => setPrimary(theme.colors.primary)).catch(() => {});
    } catch {
      /* ignore */
    }
  }, []);

  const applyPreset = async () => {
    const preset = presets.find((p) => p.id === presetId);
    const color = preset?.primary || primary;
    const patch: ThemePatch = { colors: { primary: color, bullish: color } };
    if (preset?.scheme === 'light' || preset?.scheme === 'dark') patch.scheme = preset.scheme;
    await eclipseSdk.design.apply(patch);
    setPrimary(color);
    await useThemeStore.getState().hydrateFromServer();
    setNote(`Applied ${preset?.label ?? color}`);
  };

  const reset = async () => {
    await eclipseSdk.design.reset();
    await useThemeStore.getState().hydrateFromServer();
    setNote('Design reset to the shipped default');
  };

  return (
    <Section title="Design" icon={Palette}>
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Preset accent">
          <select className={inputClass} value={presetId} onChange={(e) => setPresetId(e.target.value)}>
            <option value="">Brand color only</option>
            {presets.map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}
          </select>
        </Field>
        <Field label="Primary">
          <input type="color" value={primary} onChange={(e) => setPrimary(e.target.value)} className="h-8 w-14 rounded border border-border/40 bg-transparent" />
        </Field>
        <button type="button" onClick={() => void applyPreset()} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs">
          Apply design
        </button>
        <button type="button" onClick={() => void reset()} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs">
          Reset
        </button>
      </div>
      {note && <p className="mt-2 text-[10px] text-emerald-300">{note}</p>}
    </Section>
  );
}

// ── locks ────────────────────────────────────────────────────────────────────

function LockSection({ onChanged }: { onChanged: () => void }) {
  const [locks, setLocks] = useState<SdkLock[]>([]);
  const [resourceType, setResourceType] = useState<SdkLock['resourceType']>('page');
  const [resourceId, setResourceId] = useState('');
  const [passphrase, setPassphrase] = useState('');
  const [hint, setHint] = useState('');
  const [note, setNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const { locks: list } = await eclipseSdk.locks.list();
      setLocks(list);
    } catch {
      setLocks([]);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const create = async () => {
    await eclipseSdk.locks.create({
      resourceType, resourceId: resourceId.trim(), passphrase, hint: hint || undefined,
    });
    setNote(`Locked ${resourceType} "${resourceId.trim()}"`);
    setPassphrase('');
    await refresh();
    onChanged();
  };

  const unlock = async (lock: SdkLock) => {
    const secret = window.prompt(`Passphrase for ${lock.label || lock.resourceId}${lock.hint ? ` (${lock.hint})` : ''}`);
    if (!secret) return;
    try {
      await eclipseSdk.locks.unlock(lock.id, secret);
      setNote(`Unlocked ${lock.resourceId} — mutations now carry the token`);
    } catch (err) {
      setNote(errorMessage(err));
    }
  };

  const remove = async (lock: SdkLock) => {
    try {
      await eclipseSdk.locks.remove(lock.id);
      setNote(`Removed lock on ${lock.resourceId}`);
      await refresh();
      onChanged();
    } catch (err) {
      setNote(`${errorMessage(err)} (unlock it first)`);
    }
  };

  return (
    <Section title="Locks" icon={Lock} action={<span className="text-[10px] text-muted-foreground">{locks.length} locks</span>}>
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Resource">
          <select className={inputClass} value={resourceType} onChange={(e) => setResourceType(e.target.value as SdkLock['resourceType'])}>
            {LOCK_RESOURCES.map((type) => <option key={type} value={type}>{type}</option>)}
          </select>
        </Field>
        <Field label="Resource id" hint="widget = <pageId>:<instanceId>; design = global">
          <input className={inputClass} value={resourceId} onChange={(e) => setResourceId(e.target.value)} />
        </Field>
        <Field label="Passphrase"><input type="password" className={inputClass} value={passphrase} onChange={(e) => setPassphrase(e.target.value)} /></Field>
        <Field label="Hint (optional)"><input className={inputClass} value={hint} onChange={(e) => setHint(e.target.value)} /></Field>
        <div className="flex items-end">
          <button type="button" onClick={() => void create()} disabled={!resourceId.trim() || passphrase.length < 4} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs disabled:opacity-50">
            <Lock size={13} /> Create lock
          </button>
        </div>
      </div>
      {note && <p className="mt-2 text-[10px] text-amber-300">{note}</p>}
      <div className="mt-3 max-h-40 space-y-1 overflow-y-auto">
        {locks.length === 0 && <p className="text-[11px] italic text-muted-foreground/70">No locks. Add one to protect a page, widget, portfolio or the app design.</p>}
        {locks.map((lock) => (
          <div key={lock.id} className="flex items-center justify-between gap-2 rounded-lg border border-border/20 px-2 py-1.5">
            <div className="min-w-0">
              <p className="truncate text-xs text-foreground">{lock.label || lock.resourceId}</p>
              <p className="truncate font-mono text-[9px] text-muted-foreground/60">{lock.resourceType} · {lock.resourceId}</p>
            </div>
            <div className="flex shrink-0 gap-1">
              <button type="button" onClick={() => void unlock(lock)} className="glass-button rounded px-2 py-1 text-[10px]">Unlock</button>
              <button type="button" onClick={() => void remove(lock)} title="Remove lock" className="rounded p-1 text-muted-foreground hover:text-rose-300"><Trash2 size={12} /></button>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ── screen ───────────────────────────────────────────────────────────────────

export function SdkScreen() {
  const [caps, setCaps] = useState<SdkCapabilities | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const next = await eclipseSdk.capabilities();
      setCaps(next);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const runtimeOk = caps?.runtime === 'available';
  const summary = useMemo(() => {
    if (!caps) return 'reading runtime…';
    if (!runtimeOk) return 'Python runtime unavailable — design still works';
    return `runtime available · ${caps.widgets.count ?? 0} user widgets · ${caps.locks.count ?? 0} locks`;
  }, [caps, runtimeOk]);

  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl font-semibold text-foreground">Eclipse SDK</h1>
          <p className="text-xs text-muted-foreground">
            Create widgets, compose pages, build funds, restyle the app and lock what should not change.
          </p>
        </div>
        <button type="button" onClick={() => void refresh()} disabled={busy} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs disabled:opacity-50">
          <RefreshCw size={13} /> {busy ? 'Checking…' : 'Refresh'}
        </button>
      </header>

      <div className={cn('glass-card-subtle rounded-lg px-3 py-2 text-[11px]', error ? 'text-rose-300' : runtimeOk ? 'text-emerald-300' : 'text-amber-300')}>
        {error ? `SDK: ${error}` : summary}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-y-auto xl:grid-cols-2">
        <WidgetSection onChanged={() => void refresh()} />
        <PageSection onChanged={() => void refresh()} />
        <PortfolioSection onChanged={() => void refresh()} />
        <DesignSection caps={caps} />
        <LockSection onChanged={() => void refresh()} />
      </div>
    </div>
  );
}
