"use client";

import { normalizePresetBackground } from "@/lib/backgrounds";
import {
  THEME_PRESETS,
  auroraFromColors,
  normalizeTheme,
  themePresetId,
  useThemeStore,
  type ThemePreset,
} from "@/lib/theme";
import { PresetTile } from "@/components/screens/theme-preview";
import { cn } from "@/lib/utils";

/**
 * First-run appearance step. The theme store is the single source of truth, so
 * picking a tile applies the look live (the wizard itself recolors) and persists
 * it app-wide through the same path Settings › Customization uses. That means a
 * user never finishes onboarding into a different look than the one they picked.
 */
export function ThemeStep() {
  const theme = useThemeStore((s) => s.theme);
  const userPresets = useThemeStore((s) => s.userPresets);
  const applyPreset = useThemeStore((s) => s.applyPreset);
  const applyUserPreset = useThemeStore((s) => s.applyUserPreset);

  const activeShipped = themePresetId(theme);
  const normalized = normalizeTheme(theme);
  const activeUser = userPresets.find(
    (preset) => JSON.stringify(normalizeTheme(preset.theme)) === JSON.stringify(normalized),
  )?.id;

  const selectShipped = (preset: ThemePreset) => {
    // Mirror the Settings panel: a preset carries its backdrop and ambient glow,
    // and the Aurora fallback derives from its colors when it has no snapshot.
    applyPreset(
      normalizeTheme(preset.theme),
      normalizePresetBackground(preset.background),
      preset.aurora ?? auroraFromColors(preset.theme.colors),
    );
  };

  return (
    <div className="space-y-6">
      <p className="rounded-xl border border-white/10 bg-white/[0.02] p-3 text-[11.5px] leading-relaxed text-muted-foreground">
        Pick a look and the whole app — including this screen — changes with it.
        Your choice is saved app-wide, so every window opens the same way. You can
        fine-tune colors, glass and fonts later in{" "}
        <span className="font-medium text-foreground">Settings › Customization</span>.
      </p>

      {userPresets.length > 0 && (
        <section>
          <p className="text-[12px] font-semibold text-foreground">Your saved themes</p>
          <p className="mt-0.5 text-[11.5px] text-muted-foreground">
            Presets you saved earlier on this install.
          </p>
          <div className="mt-2.5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {userPresets.map((preset) => (
              <PresetTile
                key={preset.id}
                theme={normalizeTheme(preset.theme)}
                label={preset.label}
                description="Your saved theme"
                active={activeUser === preset.id}
                onClick={() => applyUserPreset(preset.id)}
              />
            ))}
          </div>
        </section>
      )}

      <section>
        <p className="text-[12px] font-semibold text-foreground">Built-in looks</p>
        <p className="mt-0.5 text-[11.5px] text-muted-foreground">
          Dark terminals, glassy surfaces and a few light options.
        </p>
        <div className="mt-2.5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {THEME_PRESETS.map((preset) => (
            <PresetTile
              key={preset.id}
              theme={preset.theme}
              label={preset.label}
              description={preset.description}
              active={activeShipped === preset.id}
              onClick={() => selectShipped(preset)}
            />
          ))}
        </div>
      </section>

      <p className={cn("text-[11px] leading-relaxed text-muted-foreground/70")}>
        Currently using{" "}
        <span className="font-medium text-foreground">
          {theme.appName || "Eclipse"}
        </span>
        {" · "}
        {theme.scheme === "light" ? "light" : "dark"} scheme.
      </p>
    </div>
  );
}
