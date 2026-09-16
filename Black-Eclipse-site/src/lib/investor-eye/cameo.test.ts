import { describe, it, expect } from 'vitest';
import {
  classifyCameo, quadClassOf, severityFromGoldstein, fipsToIso2, cameoActorToIso2, dyadCountries,
} from './cameo';

describe('classifyCameo', () => {
  it('maps CAMEO root codes to event types', () => {
    expect(classifyCameo('190')).toBe('conflict');   // 19 fight
    expect(classifyCameo('1823')).toBe('conflict');  // 18 assault
    expect(classifyCameo('172')).toBe('sanction');   // 17 coerce
    expect(classifyCameo('141')).toBe('protest');    // 14 protest
    expect(classifyCameo('042')).toBe('diplomatic'); // 04 consult
    expect(classifyCameo('061')).toBe('trade');      // 06 material cooperation
  });

  it('never softens a material-conflict code with a keyword override', () => {
    // A fight story that happens to mention oil must stay a conflict.
    expect(classifyCameo('190', { type: 'energy' })).toBe('conflict');
    expect(classifyCameo('1823', { type: 'trade' })).toBe('conflict');
  });

  it('allows an override on a cooperative code', () => {
    expect(classifyCameo('042', { type: 'energy' })).toBe('energy');
  });

  it('does not override into the generic diplomatic bucket', () => {
    expect(classifyCameo('042', { type: 'diplomatic' })).toBe('diplomatic');
  });

  it('falls back to other for unknown codes', () => {
    expect(classifyCameo('999')).toBe('other');
    expect(classifyCameo('')).toBe('other');
  });
});

describe('quadClassOf', () => {
  it('parses valid quad classes', () => {
    expect(quadClassOf('1')).toBe(1);
    expect(quadClassOf('4')).toBe(4);
  });
  it('rejects invalid values', () => {
    expect(quadClassOf('9')).toBeUndefined();
    expect(quadClassOf(undefined)).toBeUndefined();
  });
});

describe('severityFromGoldstein', () => {
  it('maps the Goldstein scale to severity', () => {
    expect(severityFromGoldstein(-10, true)).toBe('critical');
    expect(severityFromGoldstein(-8, true)).toBe('critical');
    expect(severityFromGoldstein(-5, true)).toBe('high');
    expect(severityFromGoldstein(-1, false)).toBe('medium');
    expect(severityFromGoldstein(5, false)).toBe('low');
  });

  it('defaults using material-conflict knowledge when unspecified', () => {
    expect(severityFromGoldstein(undefined, true)).toBe('high');
    expect(severityFromGoldstein(undefined, false)).toBe('medium');
  });
});

describe('fipsToIso2', () => {
  it('maps FIPS codes that SHADOW ISO codes correctly', () => {
    // These are the traps: using the FIPS code as ISO would misplace events.
    expect(fipsToIso2('AS')).toBe('AU'); // FIPS Australia (ISO AS = American Samoa)
    expect(fipsToIso2('CH')).toBe('CN'); // FIPS China (ISO CH = Switzerland)
    expect(fipsToIso2('SZ')).toBe('CH'); // FIPS Switzerland (ISO SZ = Eswatini)
    expect(fipsToIso2('SF')).toBe('ZA'); // FIPS South Africa
    expect(fipsToIso2('UK')).toBe('GB'); // FIPS United Kingdom
  });

  it('maps common countries', () => {
    expect(fipsToIso2('US')).toBe('US');
    expect(fipsToIso2('RS')).toBe('RU');
    expect(fipsToIso2('PK')).toBe('PK');
  });

  it('returns undefined for unknown or empty input', () => {
    expect(fipsToIso2('ZZ')).toBeUndefined();
    expect(fipsToIso2('')).toBeUndefined();
    expect(fipsToIso2(undefined)).toBeUndefined();
  });
});

describe('cameoActorToIso2', () => {
  it('maps 3-letter actor country codes', () => {
    expect(cameoActorToIso2('USA')).toBe('US');
    expect(cameoActorToIso2('RUS')).toBe('RU');
    expect(cameoActorToIso2('CHN')).toBe('CN');
  });

  it('falls back to the gazetteer for unlisted ISO-3 codes', () => {
    expect(cameoActorToIso2('KEN')).toBe('KE');
  });

  it('rejects placeholders and wrong lengths', () => {
    expect(cameoActorToIso2('---')).toBeUndefined();
    expect(cameoActorToIso2('US')).toBeUndefined();
    expect(cameoActorToIso2(undefined)).toBeUndefined();
  });
});

describe('dyadCountries', () => {
  it('returns action country first, then the actor pair, de-duplicated', () => {
    expect(dyadCountries('RS', 'USA', 'RUS')).toEqual(['RU', 'US']);
  });

  it('includes both actors when the action geo is elsewhere', () => {
    // A meeting in Belgium between the US and China.
    expect(dyadCountries('BE', 'USA', 'CHN')).toEqual(['BE', 'US', 'CN']);
  });

  it('drops unresolvable codes', () => {
    expect(dyadCountries(undefined, 'USA', undefined)).toEqual(['US']);
    expect(dyadCountries('ZZ', undefined, undefined)).toEqual([]);
  });
});
