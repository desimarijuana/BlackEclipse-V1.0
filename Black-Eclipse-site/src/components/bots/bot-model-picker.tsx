'use client';

// Per-bot model picker. A bot's scheduled runs use the app's configured default
// model unless it pins its OWN here; the choice is stored on the automation's
// action config and honored by the engine's dispatcher (`_model_settings_for`).
// This deliberately does NOT reuse the chat composer's selector, which persists
// its choice as the GLOBAL default — a bot's model must not change the app's.
//
// The catalog can be slow on a cold Python runtime, so this shows loading,
// a "runtime starting" hint, an error with Retry, and an honest "no provider"
// message instead of a silent empty dropdown.

import { useCallback, useEffect, useState } from 'react';
import { useT } from '@/lib/i18n';
import { RefreshCw } from '@/lib/icons';
import { cn } from '@/lib/utils';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface ProviderOption {
  id: string;
  label: string;
  available?: boolean;
  keyless?: boolean;
  models?: string[];
}

const DEFAULT_VALUE = '__default__';

function encode(provider: string, model: string): string {
  return JSON.stringify({ provider, model });
}

export interface BotModelPickerProps {
  provider: string;
  model: string;
  onChange: (patch: { modelProvider: string; model: string }) => void;
}

export function BotModelPicker({ provider, model, onChange }: BotModelPickerProps) {
  const t = useT();
  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);
  const [warmup, setWarmup] = useState(false);

  const load = useCallback(async () => {
    setPhase('loading');
    setError(null);
    try {
      const response = await fetch('/api/harness/chat/models', {
        signal: AbortSignal.timeout(60_000),
      });
      if (!response.ok) throw new Error(`model catalog returned ${response.status}`);
      const body = (await response.json()) as { providers?: ProviderOption[] };
      setProviders(Array.isArray(body.providers) ? body.providers : []);
      setPhase('ready');
    } catch (err) {
      setProviders([]);
      setPhase('error');
      setError(err instanceof Error ? err.message : 'could not read the model catalog');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (phase !== 'loading') {
      setWarmup(false);
      return;
    }
    const timer = setTimeout(() => setWarmup(true), 3000);
    return () => clearTimeout(timer);
  }, [phase]);

  const value = model ? encode(provider, model) : DEFAULT_VALUE;
  const usable = providers.filter((p) => (p.keyless || p.available) && (p.models?.length ?? 0) > 0);
  // Keep an already-pinned model selectable even if the catalog has not loaded.
  const pinnedMissing = Boolean(model) && !usable.some((p) => p.models?.includes(model));

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-medium text-muted-foreground">{t('bots.model.label')}</div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={phase === 'loading'}
          aria-label="Refresh models"
          className="rounded p-0.5 text-muted-foreground hover:bg-white/5 hover:text-foreground disabled:opacity-50"
        >
          <RefreshCw size={11} className={cn(phase === 'loading' && 'animate-spin')} />
        </button>
      </div>
      <Select
        value={value}
        onValueChange={(v) => {
          if (!v || v === DEFAULT_VALUE) {
            onChange({ modelProvider: '', model: '' });
            return;
          }
          try {
            const parsed = JSON.parse(v) as { provider: string; model: string };
            onChange({ modelProvider: parsed.provider, model: parsed.model });
          } catch {
            /* ignore a malformed value */
          }
        }}
      >
        <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
        <SelectContent className="max-h-72 overflow-y-auto">
          <SelectItem value={DEFAULT_VALUE}>{t('bots.model.default')}</SelectItem>
          {pinnedMissing && (
            <SelectItem value={encode(provider, model)}>{provider ? `${provider} / ` : ''}{model}</SelectItem>
          )}
          {usable.map((p) =>
            (p.models ?? []).map((m) => (
              <SelectItem key={`${p.id}:${m}`} value={encode(p.id, m)}>{p.label} / {m}</SelectItem>
            )),
          )}
        </SelectContent>
      </Select>

      {phase === 'loading' && (
        <p className="text-[10px] text-muted-foreground">
          {warmup ? 'Agent runtime is starting — models will appear shortly…' : 'Loading models…'}
        </p>
      )}
      {phase === 'error' && (
        <p className="text-[10px] text-amber-300">
          {error}{' '}
          <button type="button" onClick={() => void load()} className="underline">
            Retry
          </button>
        </p>
      )}
      {phase === 'ready' && usable.length === 0 && (
        <p className="text-[10px] text-amber-300">
          No usable provider. Add an API key in Settings › Providers, or start Ollama.
        </p>
      )}
      {phase === 'ready' && usable.length > 0 && !model && (
        <p className="text-[10px] text-muted-foreground">
          Unpinned bots use the app's default model.
        </p>
      )}
    </div>
  );
}
