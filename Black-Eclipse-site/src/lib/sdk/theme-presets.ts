import { getConfig, setConfig } from '@/lib/settings';
import type { EclipseTheme } from '@/lib/theme/tokens';
import { buildThemeFromSpec, normalizeThemeSpec, type ThemeSpec } from './theme-spec';

export const THEME_PRESETS_CONFIG_KEY = 'eclipse_theme_presets';
const MAX_PRESETS = 50;

export interface SavedThemePreset {
  name: string;
  spec: ThemeSpec;
  createdAt: string;
  updatedAt: string;
}

export interface SavedThemePresetView extends SavedThemePreset {
  theme: EclipseTheme;
}

function cleanName(raw: unknown): string {
  const name = typeof raw === 'string' ? raw.trim() : '';
  if (!name) throw new Error('a theme preset name is required');
  if (name.length > 60) throw new Error('a theme preset name is limited to 60 characters');
  if (/[/\\\u0000-\u001f]/.test(name)) throw new Error('a theme preset name cannot contain slashes or control characters');
  return name;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

async function readPresets(): Promise<SavedThemePreset[]> {
  const raw = await getConfig(THEME_PRESETS_CONFIG_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const out: SavedThemePreset[] = [];
    for (const entry of parsed) {
      if (!isRecord(entry) || typeof entry.name !== 'string' || !isRecord(entry.spec)) continue;
      try {
        out.push({
          name: cleanName(entry.name),
          spec: normalizeThemeSpec(entry.spec),
          createdAt: typeof entry.createdAt === 'string' ? entry.createdAt : new Date(0).toISOString(),
          updatedAt: typeof entry.updatedAt === 'string' ? entry.updatedAt : new Date(0).toISOString(),
        });
      } catch {
        /* skip an invalid stored preset rather than failing the list */
      }
    }
    return out;
  } catch {
    return [];
  }
}

function view(preset: SavedThemePreset): SavedThemePresetView {
  return { ...preset, theme: buildThemeFromSpec(preset.spec) };
}

export async function listSavedThemePresets(): Promise<SavedThemePresetView[]> {
  return (await readPresets())
    .map((preset) => {
      try {
        return view(preset);
      } catch {
        return null;
      }
    })
    .filter((preset): preset is SavedThemePresetView => preset !== null);
}

export async function findSavedThemePreset(name: string): Promise<SavedThemePresetView | null> {
  const wanted = cleanName(name).toLowerCase();
  const presets = await listSavedThemePresets();
  return presets.find((preset) => preset.name.toLowerCase() === wanted) ?? null;
}

export async function saveSavedThemePreset(name: string, rawSpec: unknown): Promise<SavedThemePresetView> {
  const clean = cleanName(name);
  const spec = normalizeThemeSpec(rawSpec);
  const presets = await readPresets();
  const key = clean.toLowerCase();
  const index = presets.findIndex((preset) => preset.name.toLowerCase() === key);
  const now = new Date().toISOString();
  if (index < 0 && presets.length >= MAX_PRESETS) {
    throw new Error(`at most ${MAX_PRESETS} named theme presets are supported`);
  }
  const record: SavedThemePreset = {
    name: clean,
    spec,
    createdAt: index >= 0 ? presets[index].createdAt : now,
    updatedAt: now,
  };
  if (index >= 0) presets[index] = record;
  else presets.push(record);
  await setConfig(THEME_PRESETS_CONFIG_KEY, JSON.stringify(presets));
  return view(record);
}

export async function deleteSavedThemePreset(name: string): Promise<boolean> {
  const key = cleanName(name).toLowerCase();
  const presets = await readPresets();
  const next = presets.filter((preset) => preset.name.toLowerCase() !== key);
  if (next.length === presets.length) return false;
  await setConfig(THEME_PRESETS_CONFIG_KEY, JSON.stringify(next));
  return true;
}
