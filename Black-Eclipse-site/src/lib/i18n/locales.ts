// ── Locale registry ──────────────────────────────────────────────────────────
// The canonical list of languages BlackEclipse can render its interface in.
// `nativeName` is what we show in the language picker (a user looking for their
// own language should recognize it without reading English). `dir` drives the
// document direction — Arabic, Urdu, Persian and Hebrew flip the whole shell.
//
// This is presentation-layer only: selecting a locale changes UI chrome, never
// stored financial data or API payloads.

export type LocaleCode =
  | 'en' | 'zh' | 'hi' | 'es' | 'ar' | 'fr' | 'bn' | 'pt' | 'ru' | 'ur'
  | 'id' | 'de' | 'ja' | 'tr' | 'ko' | 'it' | 'nl' | 'fa' | 'pl' | 'vi'
  | 'th' | 'he';

export type TextDirection = 'ltr' | 'rtl';

export interface LocaleDef {
  code: LocaleCode;
  /** English name, for screen readers and logs. */
  name: string;
  /** Self-name shown in the picker. */
  nativeName: string;
  dir: TextDirection;
}

export const LOCALES: LocaleDef[] = [
  { code: 'en', name: 'English', nativeName: 'English', dir: 'ltr' },
  { code: 'zh', name: 'Chinese (Mandarin)', nativeName: '中文（普通话）', dir: 'ltr' },
  { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी', dir: 'ltr' },
  { code: 'es', name: 'Spanish', nativeName: 'Español', dir: 'ltr' },
  { code: 'ar', name: 'Arabic', nativeName: 'العربية', dir: 'rtl' },
  { code: 'fr', name: 'French', nativeName: 'Français', dir: 'ltr' },
  { code: 'bn', name: 'Bengali', nativeName: 'বাংলা', dir: 'ltr' },
  { code: 'pt', name: 'Portuguese', nativeName: 'Português', dir: 'ltr' },
  { code: 'ru', name: 'Russian', nativeName: 'Русский', dir: 'ltr' },
  { code: 'ur', name: 'Urdu', nativeName: 'اردو', dir: 'rtl' },
  { code: 'id', name: 'Indonesian', nativeName: 'Bahasa Indonesia', dir: 'ltr' },
  { code: 'de', name: 'German', nativeName: 'Deutsch', dir: 'ltr' },
  { code: 'ja', name: 'Japanese', nativeName: '日本語', dir: 'ltr' },
  { code: 'tr', name: 'Turkish', nativeName: 'Türkçe', dir: 'ltr' },
  { code: 'ko', name: 'Korean', nativeName: '한국어', dir: 'ltr' },
  { code: 'it', name: 'Italian', nativeName: 'Italiano', dir: 'ltr' },
  { code: 'nl', name: 'Dutch', nativeName: 'Nederlands', dir: 'ltr' },
  { code: 'fa', name: 'Persian', nativeName: 'فارسی', dir: 'rtl' },
  { code: 'pl', name: 'Polish', nativeName: 'Polski', dir: 'ltr' },
  { code: 'vi', name: 'Vietnamese', nativeName: 'Tiếng Việt', dir: 'ltr' },
  { code: 'th', name: 'Thai', nativeName: 'ไทย', dir: 'ltr' },
  { code: 'he', name: 'Hebrew', nativeName: 'עברית', dir: 'rtl' },
];

export const DEFAULT_LOCALE: LocaleCode = 'en';

const BY_CODE = new Map<string, LocaleDef>(LOCALES.map((l) => [l.code, l]));

/** Resolve a locale code, falling back to the default when unknown. */
export function resolveLocale(code: string | null | undefined): LocaleDef {
  return (code && BY_CODE.get(code)) || BY_CODE.get(DEFAULT_LOCALE)!;
}

/** The document direction for a locale code. */
export function localeDirection(code: string | null | undefined): TextDirection {
  return resolveLocale(code).dir;
}
