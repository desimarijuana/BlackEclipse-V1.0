import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import { designLockBlocked } from '@/lib/sdk/locks-server';
import {
  DEFAULT_ECLIPSE_THEME,
  THEME_PRESETS,
  normalizeTheme,
} from '@/lib/theme/tokens';
import {
  clearServerTheme,
  getServerThemeState,
  setServerTheme,
} from '@/lib/theme/server';
import { recordSdkAudit } from './audit-server';
import { baseDesignTheme, mergeThemePatch } from './design';
import { ThemeSpecError, buildThemeFromSpec, normalizeThemeSpec } from './theme-spec';
import {
  deleteSavedThemePreset,
  findSavedThemePreset,
  listSavedThemePresets,
  saveSavedThemePreset,
} from './theme-presets';

function fail(message: string, status = 400): NextResponse {
  return NextResponse.json({ error: message }, { status });
}

function shippedPresets() {
  return THEME_PRESETS.map(({ id, label, description, theme }) => ({
    id,
    label,
    description,
    primary: theme.colors.primary,
    scheme: theme.scheme,
  }));
}

function decodeName(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

async function auditTheme(
  request: Request,
  action: string,
  summary: string,
  resourceId = 'global',
  detail?: Record<string, unknown>,
): Promise<void> {
  await recordSdkAudit(request, { action, summary, resourceType: 'theme', resourceId, detail });
}

export async function themeRoute(request: Request, method: string, path: string[]): Promise<NextResponse> {
  if (method !== 'GET') {
    const blocked = guardMutation(request, 'sdk-theme');
    if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
    const locked = await designLockBlocked(request);
    if (locked) return locked;
  }

  const segments = path.filter(Boolean);
  const sub = segments.slice(1);

  try {
    if (sub.length === 0) {
      if (method === 'GET') {
        const state = await getServerThemeState();
        return NextResponse.json({
          success: true,
          theme: state.theme ?? DEFAULT_ECLIPSE_THEME,
          initialized: state.initialized,
          presets: shippedPresets(),
          savedPresets: await listSavedThemePresets(),
        });
      }
      if (method === 'POST') {
        const body = (await request.json().catch(() => ({}))) as { spec?: unknown };
        const spec = normalizeThemeSpec(body.spec);
        const theme = await setServerTheme(buildThemeFromSpec(spec));
        await auditTheme(request, 'theme.create', `Created the theme "${theme.appName}"`, 'global', {
          basePreset: spec.basePreset,
          scheme: spec.scheme,
        });
        return NextResponse.json({ success: true, theme, spec });
      }
      if (method === 'PUT') {
        const body = (await request.json().catch(() => ({}))) as { patch?: unknown; theme?: unknown };
        const state = await getServerThemeState();
        const theme = body.theme
          ? normalizeTheme(body.theme)
          : mergeThemePatch(baseDesignTheme(state.theme), body.patch);
        const saved = await setServerTheme(theme);
        await auditTheme(request, 'theme.apply', 'Updated the app-wide theme');
        return NextResponse.json({ success: true, theme: saved });
      }
      if (method === 'DELETE') {
        await clearServerTheme();
        await auditTheme(request, 'theme.reset', 'Reset the app-wide theme');
        return NextResponse.json({ success: true, theme: DEFAULT_ECLIPSE_THEME });
      }
      return fail('method not allowed', 405);
    }

    if (sub[0] === 'presets') {
      if (sub.length === 1) {
        if (method === 'GET') {
          return NextResponse.json({ success: true, presets: await listSavedThemePresets() });
        }
        if (method === 'POST') {
          const body = (await request.json().catch(() => ({}))) as { name?: unknown; spec?: unknown };
          const preset = await saveSavedThemePreset(String(body.name ?? ''), body.spec);
          await auditTheme(request, 'theme.preset_save', `Saved the theme preset "${preset.name}"`, preset.name);
          return NextResponse.json({ success: true, preset });
        }
        return fail('method not allowed', 405);
      }

      if (sub.length === 2 && sub[1] === 'apply' && method === 'POST') {
        const body = (await request.json().catch(() => ({}))) as { preset?: unknown };
        const wanted = String(body.preset ?? '').trim();
        if (!wanted) return fail('a preset id or name is required');
        const shipped = THEME_PRESETS.find(
          (preset) => preset.id.toLowerCase() === wanted.toLowerCase()
            || preset.label.toLowerCase() === wanted.toLowerCase(),
        );
        if (shipped) {
          const theme = await setServerTheme(shipped.theme);
          await auditTheme(request, 'theme.apply_preset', `Applied the theme preset "${shipped.label}"`, shipped.id);
          return NextResponse.json({
            success: true,
            theme,
            preset: { kind: 'shipped', id: shipped.id, label: shipped.label },
          });
        }
        const saved = await findSavedThemePreset(wanted);
        if (!saved) return fail(`unknown theme preset "${wanted}"`, 404);
        const theme = await setServerTheme(saved.theme);
        await auditTheme(request, 'theme.apply_preset', `Applied the theme preset "${saved.name}"`, saved.name);
        return NextResponse.json({
          success: true,
          theme,
          preset: { kind: 'saved', name: saved.name, label: saved.name, spec: saved.spec },
        });
      }

      if (sub.length === 2 && method === 'DELETE') {
        const name = decodeName(sub[1]);
        const shipped = THEME_PRESETS.some(
          (preset) => preset.id.toLowerCase() === name.toLowerCase()
            || preset.label.toLowerCase() === name.toLowerCase(),
        );
        if (shipped) return fail('shipped theme presets cannot be deleted');
        const removed = await deleteSavedThemePreset(name);
        if (!removed) return fail(`unknown theme preset "${name}"`, 404);
        await auditTheme(request, 'theme.preset_delete', `Deleted the theme preset "${name}"`, name);
        return NextResponse.json({ success: true, removed: true });
      }

      return fail('unknown theme preset route', 404);
    }

    return fail('unknown theme route', 404);
  } catch (err) {
    if (err instanceof ThemeSpecError) {
      return NextResponse.json({ error: err.message, issues: err.issues }, { status: 400 });
    }
    return fail(err instanceof Error ? err.message : 'theme request failed', 500);
  }
}
