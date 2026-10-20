'use client';

import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Save, Trash2 } from '@/lib/icons';
import { eclipseSdk, type SdkSavedThemePreset } from '@/lib/sdk';
import { themeToSpec } from '@/lib/sdk/theme-spec';
import { normalizeTheme, useThemeStore, type EclipseTheme } from '@/lib/theme';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { PresetTile } from './theme-preview';

interface Note {
  text: string;
  tone: 'ok' | 'error';
}

/**
 * Named presets stored app-wide in JDDS (`eclipse_theme_presets`) — available
 * to chat/SDK and every browser. Browser-local presets (chart palette, backdrop,
 * aurora) stay in the theme store and are rendered separately by the caller.
 */
export function AppWideThemePresets({ theme }: { theme: EclipseTheme }) {
  const [presets, setPresets] = useState<SdkSavedThemePreset[]>([]);
  const [name, setName] = useState('');
  const [note, setNote] = useState<Note | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const { presets: list } = await eclipseSdk.theme.listPresets();
      setPresets(list);
      setNote(null);
    } catch (err) {
      setPresets([]);
      setNote({ tone: 'error', text: err instanceof Error ? err.message : 'app-wide presets unavailable' });
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const apply = async (preset: SdkSavedThemePreset) => {
    setBusy(true);
    setNote(null);
    try {
      await eclipseSdk.theme.applyPreset(preset.name);
      await useThemeStore.getState().hydrateFromServer();
      setNote({ tone: 'ok', text: `Applied app-wide preset "${preset.name}".` });
    } catch (err) {
      setNote({ tone: 'error', text: err instanceof Error ? err.message : 'Could not apply the app-wide preset' });
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    const clean = name.trim();
    if (!clean) return;
    setBusy(true);
    setNote(null);
    try {
      await eclipseSdk.theme.savePreset(clean, themeToSpec(theme, clean));
      setName('');
      setNote({ tone: 'ok', text: `Saved app-wide preset "${clean}".` });
      await refresh();
    } catch (err) {
      setNote({ tone: 'error', text: err instanceof Error ? err.message : 'Could not save the app-wide preset' });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (preset: SdkSavedThemePreset) => {
    setBusy(true);
    setNote(null);
    try {
      await eclipseSdk.theme.deletePreset(preset.name);
      setNote({ tone: 'ok', text: `Deleted app-wide preset "${preset.name}".` });
      await refresh();
    } catch (err) {
      setNote({ tone: 'error', text: err instanceof Error ? err.message : 'Could not delete the app-wide preset' });
    } finally {
      setBusy(false);
    }
  };

  const isActive = (preset: SdkSavedThemePreset) => (
    JSON.stringify(normalizeTheme(preset.theme)) === JSON.stringify(normalizeTheme(theme))
  );

  return (
    <div className="mt-3 rounded-xl border border-border/20 glass-card-subtle p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-foreground">App-wide presets</p>
          <p className="text-[10px] text-muted-foreground">
            Saved on the server — available to chat, the SDK and every browser.
          </p>
        </div>
        <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={() => void refresh()} disabled={busy}>
          <RefreshCw className="w-3.5 h-3.5 mr-1" /> Refresh
        </Button>
      </div>
      {presets.length === 0 ? (
        <p className="text-[11px] italic text-muted-foreground/70">
          No app-wide presets yet. Save the current theme below.
        </p>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {presets.map((preset) => (
            <div key={preset.name} className="group relative">
              <PresetTile
                theme={preset.theme}
                label={preset.name}
                description="App-wide preset"
                active={isActive(preset)}
                onClick={() => void apply(preset)}
              />
              <span className="absolute top-1.5 right-1.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                <button
                  type="button"
                  title="Delete app-wide preset"
                  onClick={(event) => { event.stopPropagation(); void remove(preset); }}
                  disabled={busy}
                  className="p-1 rounded-md glass-card-strong text-muted-foreground hover:text-rose-400 cursor-pointer disabled:opacity-40"
                >
                  <Trash2 size={12} />
                </button>
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void save(); }}
          placeholder="Name this app-wide preset…"
          className="h-9 flex-1 min-w-[180px]"
        />
        <Button size="sm" className="rounded-xl cursor-pointer" onClick={() => void save()} disabled={busy || !name.trim()}>
          <Save className="w-3.5 h-3.5 mr-1" /> Save app-wide
        </Button>
      </div>
      {note && (
        <p className={cn('mt-2 text-[10px]', note.tone === 'ok' ? 'text-emerald-300' : 'text-rose-300')}>
          {note.text}
        </p>
      )}
    </div>
  );
}
