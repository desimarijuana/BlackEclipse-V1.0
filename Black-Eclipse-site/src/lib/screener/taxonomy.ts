// Sector / industry taxonomy normalization for the market screener.
//
// JDDS was populated from several import sources that used different
// classification taxonomies, so the SAME real sector is stored under two labels
// (e.g. "Financial Services" from one source and "Financials" from another).
// Left as-is, the dropdown offers both and filtering by one silently hides the
// other's rows — users read that as "the sector filter is broken".
//
// This module maps each known synonym to ONE canonical label. It is applied on
// READ (so the table renders the canonical value), on FILTER (so a canonical
// selection matches every raw synonym), and on the dropdown options (so each
// sector appears once). Values with no mapping pass through unchanged.

/** Display value for a null sector/industry. Shared by the API and the UI so
 *  the table cell and the filter option always agree. */
export const UNCLASSIFIED = 'Unclassified';

// ── Sector synonyms → canonical ────────────────────────────────────────────
// Only unambiguous pairs are merged. Taxonomies that are genuinely different
// (e.g. GICS "Technology" vs Yahoo "Technology Services"/"Electronic
// Technology") are deliberately NOT merged.
const SECTOR_ALIASES: Record<string, string> = {
  // GICS label → Yahoo/GICS hybrid label used by most of the US universe.
  'Financials': 'Financial Services',
  'Consumer Discretionary': 'Consumer Cyclical',
  'Consumer Staples': 'Consumer Defensive',
  // Crypto category spelling variants.
  'Payment': 'Payments',
  'Meme': 'Meme Coins',
};

// ── Industry synonyms → canonical ──────────────────────────────────────────
const INDUSTRY_ALIASES: Record<string, string> = {
  // Crypto sub-category labels that carry a parenthetical or expanded form.
  'Layer 1 (L1)': 'Layer 1',
  'Layer 2 (L2)': 'Layer 2',
  'Gaming (GameFi)': 'Gaming',
  // Stablecoin sub-types collapse to the category users search for.
  'Fiat-backed Stablecoin': 'Stablecoins',
  'Stablecoin Issuer': 'Stablecoins',
  'Yield-Bearing Stablecoin': 'Stablecoins',
};

/** Canonical sector label for a stored value (null → UNCLASSIFIED). */
export function normalizeSector(value: string | null | undefined): string {
  if (!value) return UNCLASSIFIED;
  return SECTOR_ALIASES[value] ?? value;
}

/** Canonical industry label for a stored value (null → UNCLASSIFIED). */
export function normalizeIndustry(value: string | null | undefined): string {
  if (!value) return UNCLASSIFIED;
  return INDUSTRY_ALIASES[value] ?? value;
}

/** Every raw stored value that normalizes to the given canonical sector
 *  (including the canonical itself). Used to build the DB filter. */
export function rawSectorVariants(canonical: string): string[] {
  if (canonical === UNCLASSIFIED) return [];
  const variants = [canonical];
  for (const [raw, canon] of Object.entries(SECTOR_ALIASES)) {
    if (canon === canonical && raw !== canonical) variants.push(raw);
  }
  return variants;
}

/** Every raw stored value that normalizes to the given canonical industry. */
export function rawIndustryVariants(canonical: string): string[] {
  if (canonical === UNCLASSIFIED) return [];
  const variants = [canonical];
  for (const [raw, canon] of Object.entries(INDUSTRY_ALIASES)) {
    if (canon === canonical && raw !== canonical) variants.push(raw);
  }
  return variants;
}
