'use client';

// Per-bot model picker. A bot's scheduled runs use the app's configured default
// model unless it pins its OWN here; the choice is stored on the automation's
// action config and honored by the engine's dispatcher (`_model_settings_for`).
// This deliberately does NOT reuse the chat composer's selector, which persists
// its choice as the GLOBAL default — a bot's model must not change the app's.

import { useEffect, useState } from 'react';
import { useT } from '@/lib/i18n';
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

  useEffect(() => {
    let live = true;
    void fetch('/api/harness/chat/models')
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        if (live && body && Array.isArray(body.providers)) setProviders(body.providers as ProviderOption[]);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  const value = model ? encode(provider, model) : DEFAULT_VALUE;
  const usable = providers.filter((p) => (p.keyless || p.available) && (p.models?.length ?? 0) > 0);
  // Keep an already-pinned model selectable even if the catalog has not loaded.
  const pinnedMissing = Boolean(model) && !usable.some((p) => p.models?.includes(model));

  return (
    <div className="space-y-1">
      <div className="text-[11px] font-medium text-muted-foreground">{t('bots.model.label')}</div>
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
    </div>
  );
}
