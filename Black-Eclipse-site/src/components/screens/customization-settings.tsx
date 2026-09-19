"use client";

// ── Settings › Customization ──────────────────────────────────────────────
// The one place to shape the interface to the person using it: interface
// language and accessibility preferences. Both are presentation-layer only —
// they persist locally and never touch stored financial data.
//
// Language writes to the locale store, which translates chrome and sets
// <html lang/dir> (RTL for Arabic/Urdu/Persian/Hebrew). Accessibility toggles
// flip classes on <html> that globals.css responds to, so no component needs
// to read the preference.

import { Accessibility, Languages, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DEFAULT_A11Y, LOCALES, useLocaleStore, useT, type LocaleCode } from "@/lib/i18n";

function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center border rounded-full transition-colors cursor-pointer",
        checked ? "bg-primary/25 border-primary/50" : "bg-muted/60 border-border",
      )}
    >
      <span
        className={cn(
          "inline-block h-3.5 w-3.5 transform rounded-full shadow-sm transition-transform",
          checked ? "translate-x-[18px] bg-primary" : "translate-x-[2px] bg-muted-foreground/70",
        )}
      />
    </button>
  );
}

function Row({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <Label className="text-xs text-muted-foreground font-medium">{label}</Label>
        <p className="text-[10px] text-muted-foreground/70 mt-0.5">{hint}</p>
      </div>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}

export function CustomizationSettingsPanel() {
  const t = useT();
  const locale = useLocaleStore((s) => s.locale);
  const setLocale = useLocaleStore((s) => s.setLocale);
  const a11y = useLocaleStore((s) => s.a11y);
  const setA11y = useLocaleStore((s) => s.setA11y);

  return (
    <div className="space-y-6">
      {/* Language */}
      <div className="space-y-4 rounded-2xl border border-white/10 dark:border-white/5 glass-card p-5 md:p-6">
        <div className="flex items-center gap-2 text-xs text-foreground/80">
          <Languages className="w-4 h-4 text-primary shrink-0" />
          <p>{t('settings.customization.languageHint')}</p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">{t('settings.customization.language')}</Label>
          <Select value={locale} onValueChange={(v) => v && setLocale(v as LocaleCode)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LOCALES.map((l) => (
                <SelectItem key={l.code} value={l.code}>
                  <span className="inline-flex items-center gap-2">
                    {l.nativeName}
                    <span className="text-muted-foreground/60 text-[10px]">{l.name}</span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-[10px] text-muted-foreground/70 mt-0.5">
            {t('settings.customization.languageHint')}
          </p>
        </div>
      </div>

      {/* Accessibility */}
      <div className="space-y-5 rounded-2xl border border-white/10 dark:border-white/5 glass-card p-5 md:p-6">
        <div className="flex items-center gap-2 text-xs text-foreground/80">
          <Accessibility className="w-4 h-4 text-primary shrink-0" />
          <p>{t('settings.accessibility.description')}</p>
        </div>

        <Row
          label={t('settings.accessibility.reduceMotion')}
          hint={t('settings.accessibility.reduceMotionHint')}
          checked={a11y.reduceMotion}
          onChange={(v) => setA11y({ reduceMotion: v })}
        />
        <Row
          label={t('settings.accessibility.highContrast')}
          hint={t('settings.accessibility.highContrastHint')}
          checked={a11y.highContrast}
          onChange={(v) => setA11y({ highContrast: v })}
        />
        <Row
          label={t('settings.accessibility.largeText')}
          hint={t('settings.accessibility.largeTextHint')}
          checked={a11y.largeText}
          onChange={(v) => setA11y({ largeText: v })}
        />

        <div className="flex justify-end pt-1">
          <Button
            variant="outline"
            size="sm"
            className="cursor-pointer rounded-xl"
            onClick={() => setA11y(DEFAULT_A11Y)}
          >
            <RotateCcw className="w-3.5 h-3.5 mr-1" /> {t('settings.accessibility.reset')}
          </Button>
        </div>
      </div>
    </div>
  );
}
