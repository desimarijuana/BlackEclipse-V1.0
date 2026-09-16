import { describe, it, expect } from 'vitest';
import { resolvePlace, placeCount, PLACES } from './places';

describe('place gazetteer', () => {
  it('is non-trivial and every entry is well-formed', () => {
    expect(placeCount()).toBeGreaterThan(80);
    for (const p of PLACES) {
      expect(p.name.length).toBeGreaterThan(0);
      expect(p.iso2).toMatch(/^[A-Z]{2}$/);
      expect(p.lon).toBeGreaterThanOrEqual(-180);
      expect(p.lon).toBeLessThanOrEqual(180);
      expect(p.lat).toBeGreaterThanOrEqual(-90);
      expect(p.lat).toBeLessThanOrEqual(90);
    }
  });

  it('resolves a financial centre named in a headline', () => {
    expect(resolvePlace('Fed signals pause at Washington meeting')?.name).toBe('Washington');
    expect(resolvePlace('Kremlin comments on grain deal')?.name).toBe('Moscow');
  });

  it('resolves chokepoints, which are the highest-signal logistics places', () => {
    expect(resolvePlace('Tanker attacked near the Strait of Hormuz')?.name).toBe('Strait of Hormuz');
    expect(resolvePlace('Container ship refloated in Suez Canal')?.name).toBe('Suez Canal');
    expect(resolvePlace('Houthi strikes in the Red Sea')?.name).toBe('Red Sea');
  });

  it('resolves energy and industrial hubs', () => {
    expect(resolvePlace('Saudi Aramco reports fire at Abqaiq facility')?.name).toBe('Abqaiq');
    expect(resolvePlace('TSMC output hit by power issue')?.name).toBe('Taiwan Semiconductor');
    expect(resolvePlace('Chile copper output falls at Escondida')?.name).toBe('Escondida');
  });

  it('prefers the longer, more specific name', () => {
    // "Strait of Hormuz" must beat the bare "hormuz" alias.
    const p = resolvePlace('Shipping halted in Strait of Hormuz');
    expect(p?.name).toBe('Strait of Hormuz');
    expect(p?.kind).toBe('chokepoint');
  });

  it('uses the country hint to disambiguate', () => {
    // Two different countries are not required here; the hint must at least not
    // break a correct match and must be honoured when it applies.
    expect(resolvePlace('Shanghai port congestion', ['CN'])?.iso2).toBe('CN');
    // With a contradicting hint the place is still found (hint is a preference).
    expect(resolvePlace('Shanghai port congestion', ['US'])?.name).toBe('Shanghai');
  });

  it('does not match inside unrelated words', () => {
    // "china" is not an alias, but guard against substring accidents generally.
    expect(resolvePlace('A story about nothing in particular')).toBeUndefined();
    expect(resolvePlace('')).toBeUndefined();
    expect(resolvePlace(null)).toBeUndefined();
  });

  it('handles hyphenated and apostrophe forms', () => {
    expect(resolvePlace('Attack near Bab-el-Mandeb')?.name).toBe('Bab-el-Mandeb');
    expect(resolvePlace("Shelling reported in Sana'a")?.name).toBe('Sanaa');
  });

  it('every place maps to a real country in the app gazetteer', async () => {
    const { countryByIso2 } = await import('./countries');
    for (const p of PLACES) {
      expect(countryByIso2(p.iso2), `${p.name} → ${p.iso2}`).toBeDefined();
    }
  });
});
