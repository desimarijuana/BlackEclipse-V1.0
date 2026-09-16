// ── Investor Eye — CAMEO / GDELT bulk-export decoding ────────────────────────
// The GDELT 2.0 Event export is the canonical feed: every 15 minutes it
// publishes a tab-separated file of machine-coded events with actor names,
// country codes, a CAMEO event code, a Goldstein conflict/cooperation score,
// mention counts and exact action coordinates.
//
// This module decodes that format. It replaces the previous approach of asking
// GDELT's DOC API for article titles and guessing from keywords — the DOC API
// was measured to take >13s per request AND to 429, while the bulk file
// downloads in under a second, is not rate-limited, and carries far richer
// structure.
//
// Pure functions only — no I/O — so every mapping is unit-testable.

import { COUNTRIES } from './countries';
import type { EventSeverity, EventType } from './types';

// ── CAMEO root codes → the app's event types ─────────────────────────────────
// CAMEO root codes are the first two digits of the 3-4 digit EventCode.
// https://www.gdeltproject.org/data/lookups/CAMEO.eventcodes.txt
const ROOT_EVENT_TYPE: Record<string, EventType> = {
  '01': 'diplomatic',   // Make public statement
  '02': 'diplomatic',   // Appeal
  '03': 'diplomatic',   // Express intent to cooperate
  '04': 'diplomatic',   // Consult
  '05': 'diplomatic',   // Engage in diplomatic cooperation
  '06': 'trade',        // Engage in material cooperation
  '07': 'trade',        // Provide aid
  '08': 'diplomatic',   // Yield
  '09': 'regulatory',   // Investigate
  '10': 'diplomatic',   // Demand
  '11': 'diplomatic',   // Disapprove
  '12': 'diplomatic',   // Reject
  '13': 'military',     // Threaten
  '14': 'protest',      // Protest
  '15': 'military',     // Exhibit military force posture
  '16': 'sanction',     // Reduce relations
  '17': 'sanction',     // Coerce
  '18': 'conflict',     // Assault
  '19': 'conflict',     // Fight
  '20': 'conflict',     // Use unconventional mass violence
};

/**
 * Classify a CAMEO EventCode.
 *
 * `rootHint` lets a caller override a cooperative code with a more specific
 * type when the actor/URL text indicates one (e.g. "OPEC cuts output" is CAMEO
 * "consult" but is really an energy event). The override only applies when the
 * code is a COOPERATIVE one — a material-conflict code (18/19/20) is never
 * softened, because "there was a fight" outranks "the article mentions oil".
 */
export function classifyCameo(
  eventCode: string,
  overrides?: { type?: EventType; keywords?: string },
): EventType {
  const root = (eventCode ?? '').padStart(3, '0').slice(0, 2);
  const base = ROOT_EVENT_TYPE[root] ?? 'other';
  const isMaterialConflict = root === '18' || root === '19' || root === '20';
  if (!isMaterialConflict && overrides?.type && overrides.type !== 'diplomatic') {
    return overrides.type;
  }
  return base;
}

/** CAMEO QuadClass: 1=verbal coop, 2=material coop, 3=verbal conflict, 4=material conflict. */
export function quadClassOf(raw: string | undefined): 1 | 2 | 3 | 4 | undefined {
  const n = Number(raw);
  return n === 1 || n === 2 || n === 3 || n === 4 ? n : undefined;
}

/**
 * Severity. GDELT's GoldsteinScale runs -10 (most hostile) .. +10 (most
 * cooperative) and is a real, published intensity measure — far better than
 * guessing from headline adjectives.
 */
export function severityFromGoldstein(goldstein: number | undefined, isMaterialConflict: boolean): EventSeverity {
  if (goldstein === undefined || !Number.isFinite(goldstein)) return isMaterialConflict ? 'high' : 'medium';
  if (goldstein <= -8) return 'critical';
  if (goldstein <= -4) return 'high';
  if (goldstein < 0) return 'medium';
  if (goldstein < 4) return 'low';
  return 'low';
}

// ── FIPS 10-4 → ISO 3166-1 alpha-2 ───────────────────────────────────────────
// GDELT `ActionGeo_CountryCode` uses FIPS 10-4, which CONFLICTS with ISO for
// several important countries:
//   FIPS AS = Australia   (ISO AS = American Samoa)
//   FIPS CH = China       (ISO CH = Switzerland)
//   FIPS SZ = Switzerland (ISO SZ = Eswatini)
//   FIPS SF = South Africa, FIPS UK = United Kingdom
// So mapping through FIPS is mandatory — using the codes directly would put
// events in the wrong country. (The event's LAT/LON are used for the map pin;
// this table is for the country *entity*.)
let fipsTable: Record<string, string> | null = null;
const FIPS_SOURCE: Array<[string, string]> = [
  ['AF', 'AF'], ['AL', 'AL'], ['AG', 'DZ'], ['AN', 'AD'], ['AO', 'AO'], ['AR', 'AR'],
  ['AM', 'AM'], ['AS', 'AU'], ['AU', 'AT'], ['AJ', 'AZ'], ['BF', 'BS'], ['BG', 'BD'],
  ['BB', 'BB'], ['BO', 'BY'], ['BE', 'BE'], ['BH', 'BZ'], ['BN', 'BJ'], ['BT', 'BT'],
  ['BL', 'BO'], ['BK', 'BA'], ['BC', 'BW'], ['BR', 'BR'], ['BX', 'BN'], ['BU', 'BG'],
  ['UV', 'BF'], ['BM', 'MM'], ['BY', 'BI'], ['CB', 'KH'], ['CM', 'CM'], ['CA', 'CA'],
  ['CV', 'CV'], ['CT', 'CF'], ['CD', 'TD'], ['CI', 'CL'], ['CH', 'CN'], ['CO', 'CO'],
  ['CN', 'KM'], ['CF', 'CG'], ['CG', 'CD'], ['CS', 'CR'], ['HR', 'HR'], ['CU', 'CU'],
  ['CY', 'CY'], ['EZ', 'CZ'], ['DA', 'DK'], ['DJ', 'DJ'], ['DO', 'DM'], ['DR', 'DO'],
  ['EC', 'EC'], ['EG', 'EG'], ['ES', 'SV'], ['EK', 'GQ'], ['ER', 'ER'], ['EN', 'EE'],
  ['ET', 'ET'], ['FJ', 'FJ'], ['FI', 'FI'], ['FR', 'FR'], ['FG', 'GF'], ['GB', 'GA'],
  ['GA', 'GM'], ['GG', 'GE'], ['GM', 'DE'], ['GH', 'GH'], ['GR', 'GR'], ['GL', 'GL'],
  ['GT', 'GT'], ['GV', 'GN'], ['PU', 'GW'], ['GY', 'GY'], ['HA', 'HT'], ['HO', 'HN'],
  ['HK', 'HK'], ['HU', 'HU'], ['IC', 'IS'], ['IN', 'IN'], ['ID', 'ID'], ['IR', 'IR'],
  ['IZ', 'IQ'], ['EI', 'IE'], ['IS', 'IL'], ['IT', 'IT'], ['JM', 'JM'], ['JA', 'JP'],
  ['JO', 'JO'], ['KZ', 'KZ'], ['KE', 'KE'], ['KQ', 'KI'], ['KN', 'KP'], ['KS', 'KR'],
  ['KU', 'KW'], ['KG', 'KG'], ['LA', 'LA'], ['LG', 'LV'], ['LE', 'LB'], ['LT', 'LS'],
  ['LI', 'LR'], ['LY', 'LY'], ['LH', 'LT'], ['LU', 'LU'], ['MC', 'MO'], ['MK', 'MK'],
  ['MA', 'MG'], ['MI', 'MW'], ['MY', 'MY'], ['MV', 'MV'], ['ML', 'ML'], ['MT', 'MT'],
  ['RM', 'MH'], ['MR', 'MR'], ['MP', 'MU'], ['MX', 'MX'], ['FM', 'FM'], ['MD', 'MD'],
  ['MN', 'MC'], ['MG', 'MN'], ['MJ', 'ME'], ['MO', 'MA'], ['MZ', 'MZ'], ['WA', 'NA'],
  ['NR', 'NR'], ['NP', 'NP'], ['NL', 'NL'], ['NC', 'NC'], ['NZ', 'NZ'], ['NU', 'NI'],
  ['NG', 'NE'], ['NI', 'NG'], ['NO', 'NO'], ['OM', 'OM'], ['PK', 'PK'], ['PS', 'PW'],
  ['PM', 'PA'], ['PP', 'PG'], ['PA', 'PY'], ['PE', 'PE'], ['RP', 'PH'], ['PL', 'PL'],
  ['PO', 'PT'], ['QA', 'QA'], ['RO', 'RO'], ['RS', 'RU'], ['RW', 'RW'], ['WS', 'WS'],
  ['SM', 'SM'], ['SA', 'SA'], ['SG', 'SN'], ['RB', 'RS'], ['SC', 'SC'], ['SL', 'SL'],
  ['SN', 'SG'], ['LO', 'SK'], ['SI', 'SI'], ['BP', 'SB'], ['SO', 'SO'], ['SF', 'ZA'],
  ['SP', 'ES'], ['CE', 'LK'], ['SD', 'SD'], ['SR', 'SR'], ['WZ', 'SZ'], ['SW', 'SE'],
  ['SZ', 'CH'], ['SY', 'SY'], ['TW', 'TW'], ['TI', 'TJ'], ['TZ', 'TZ'], ['TH', 'TH'],
  ['TT', 'TL'], ['TO', 'TG'], ['TN', 'TO'], ['TS', 'TN'], ['TU', 'TR'], ['TX', 'TM'], ['RU', 'RU'],
  ['TK', 'TC'], ['TV', 'TV'], ['UG', 'UG'], ['UP', 'UA'], ['AE', 'AE'], ['UK', 'GB'],
  ['US', 'US'], ['UY', 'UY'], ['UZ', 'UZ'], ['NH', 'VU'], ['VE', 'VE'], ['VM', 'VN'],
  ['WY', 'YE'], ['ZA', 'ZM'], ['ZI', 'ZW'],
];

/** Convert a GDELT FIPS country code to ISO2, or undefined when unmapped. */
export function fipsToIso2(fips: string | undefined): string | undefined {
  if (!fips) return undefined;
  const key = fips.trim().toUpperCase();
  if (!key) return undefined;
  if (!fipsTable) {
    fipsTable = {};
    for (const [f, iso] of FIPS_SOURCE) fipsTable[f] = iso;
  }
  return fipsTable[key];
}

// ── CAMEO 3-letter actor country codes → ISO2 ────────────────────────────────
// Actor1CountryCode / Actor2CountryCode use CAMEO's 3-letter codes, which are
// usually ISO-3166 alpha-3 but include a few special values.
const CAMEO_SPECIAL_ACTORS: Record<string, string> = {
  USA: 'US', GBR: 'GB', CHN: 'CN', RUS: 'RU', DEU: 'DE', FRA: 'FR', JPN: 'JP',
  IND: 'IN', PAK: 'PK', IRN: 'IR', ISR: 'IL', SAU: 'SA', TUR: 'TR', UKR: 'UA',
  TWN: 'TW', KOR: 'KR', PRK: 'KP', BRA: 'BR', ZAF: 'ZA', AUS: 'AU', CAN: 'CA',
  MEX: 'MX', IDN: 'ID', NGA: 'NG', EGY: 'EG', ARE: 'AE', QAT: 'QA', IRQ: 'IQ',
  SYR: 'SY', YEM: 'YE', LBN: 'LB', AZE: 'AZ', ARM: 'AM', GEO: 'GE', KAZ: 'KZ',
  VNM: 'VN', THA: 'TH', PHL: 'PH', MYS: 'MY', SGP: 'SG', BGD: 'BD', LKA: 'LK',
  NPL: 'NP', AFG: 'AF', ARG: 'AR', CHL: 'CL', COL: 'CO', PER: 'PE', VEN: 'VE',
  ESP: 'ES', ITA: 'IT', NLD: 'NL', BEL: 'BE', CHE: 'CH', SWE: 'SE', NOR: 'NO',
  POL: 'PL', ROU: 'RO', GRC: 'GR', PRT: 'PT', IRL: 'IE', DNK: 'DK', FIN: 'FI',
  AUT: 'AT', CZE: 'CZ', HUN: 'HU', ETH: 'ET', KEN: 'KE', TZA: 'TZ', GHA: 'GH',
  MAR: 'MA', DZA: 'DZ', LBY: 'LY', SDN: 'SD', SOM: 'SO', MLI: 'ML', SEN: 'SN',
  ZWE: 'ZW', ZMB: 'ZM', MOZ: 'MZ', AGO: 'AO', CMR: 'CM', UGA: 'UG', NZL: 'NZ',
  CUB: 'CU', ECU: 'EC', BOL: 'BO', PRY: 'PY', URY: 'UY', GTM: 'GT', CRI: 'CR',
  PAN: 'PA', DOM: 'DO', HTI: 'HT', HND: 'HN', NIC: 'NI', SLV: 'SV', JAM: 'JM',
  TTO: 'TT', BHS: 'BS', HRV: 'HR', SRB: 'RS', BIH: 'BA', ALB: 'AL', BGR: 'BG',
  SVK: 'SK', SVN: 'SI', LTU: 'LT', LVA: 'LV', EST: 'EE', BLR: 'BY', MDA: 'MD',
  MNG: 'MN', KGZ: 'KG', TJK: 'TJ', TKM: 'TM', UZB: 'UZ', KHM: 'KH', LAO: 'LA',
  MMR: 'MM', PNG: 'PG', FJI: 'FJ', MUS: 'MU', MDG: 'MG', BWA: 'BW', NAM: 'NA',
  CIV: 'CI', GIN: 'GN', BFA: 'BF', BEN: 'BJ', TGO: 'TG', NER: 'NE', TCD: 'TD',
  CAF: 'CF', COG: 'CG', COD: 'CD', RWA: 'RW', BDI: 'BI', ERI: 'ER', GAB: 'GA',
  GNQ: 'GQ', GMB: 'GM', SLE: 'SL', LBR: 'LR', GNB: 'GW', MRT: 'MR', MWI: 'MW',
  SWZ: 'SZ', LSO: 'LS', DJI: 'DJ', PSE: 'PS', KWT: 'KW', OMN: 'OM', BHR: 'BH',
  JOR: 'JO', CYP: 'CY', MLT: 'MT', ISL: 'IS', LUX: 'LU', FRO: 'FO', GRL: 'GL',
  BLZ: 'BZ', GUY: 'GY', SUR: 'SR', BRB: 'BB', CPV: 'CV', STP: 'ST', SYC: 'SC',
};

/** Convert a CAMEO 3-letter actor country code to ISO2, or undefined. */
export function cameoActorToIso2(code: string | undefined): string | undefined {
  if (!code) return undefined;
  const key = code.trim().toUpperCase();
  if (!key || key === '---' || key.length !== 3) return undefined;
  return CAMEO_SPECIAL_ACTORS[key] ?? countryIso3ToIso2(key);
}

/** Fallback: match a plain ISO-3 code against the app's country gazetteer. */
let iso3Lookup: Map<string, string> | null = null;
function countryIso3ToIso2(iso3: string): string | undefined {
  if (!iso3Lookup) {
    iso3Lookup = new Map();
    for (const c of COUNTRIES) iso3Lookup.set(c.iso3.toUpperCase(), c.iso2);
  }
  return iso3Lookup.get(iso3);
}

/**
 * Extract a country-pair from a GDELT action: the action's own location plus
 * the two actors. Returned in priority order and de-duplicated, because the
 * actor pair is what makes an event *dyadic* (e.g. "US imposes sanctions on
 * Russia" has ActionGeo=US but both actors matter).
 */
export function dyadCountries(
  actionFips: string | undefined,
  actor1: string | undefined,
  actor2: string | undefined,
): string[] {
  const out: string[] = [];
  const push = (iso2: string | undefined) => { if (iso2 && !out.includes(iso2)) out.push(iso2); };
  push(fipsToIso2(actionFips));
  push(cameoActorToIso2(actor1));
  push(cameoActorToIso2(actor2));
  return out;
}
