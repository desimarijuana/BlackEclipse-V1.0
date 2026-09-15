import { describe, it, expect } from 'vitest';
import { classifyType, classifySeverity, classifyChannels, classifyCommodities, classifySectors, severityWeight, SEVERITY_RANK } from './classify';

describe('classifyType', () => {
  it('classifies conflict signals above generic economic words', () => {
    expect(classifyType('Missile strikes hit port as war escalates')).toBe('conflict');
    expect(classifyType('Oil prices rise amid the conflict')).toBe('conflict');
  });

  it('classifies sanctions and tariffs distinctly', () => {
    expect(classifyType('US announces new sanctions on banks')).toBe('sanction');
    expect(classifyType('New tariffs on imported steel')).toBe('tariff');
  });

  it('classifies energy, shipping and trade', () => {
    expect(classifyType('OPEC cuts crude oil production')).toBe('energy');
    expect(classifyType('Cargo vessel stuck in the Suez canal')).toBe('shipping');
    expect(classifyType('Trade deal signed between the two nations')).toBe('trade');
  });

  it('classifies monetary and fiscal', () => {
    expect(classifyType('Central bank signals interest rate cut')).toBe('monetary');
    expect(classifyType('Government budget deficit widens')).toBe('fiscal');
  });

  it('classifies natural disasters and cyber', () => {
    expect(classifyType('Magnitude 6.2 earthquake strikes')).toBe('natural_disaster');
    expect(classifyType('Ransomware attack hits hospitals')).toBe('cyber');
  });

  it('uses a provider hint when nothing matches', () => {
    expect(classifyType('Something happened', 'earthquake')).toBe('natural_disaster');
    expect(classifyType('Something happened', 'conflict')).toBe('conflict');
  });

  it('falls back to other', () => {
    expect(classifyType('A quiet announcement about a park')).toBe('other');
  });
});

describe('classifySeverity', () => {
  it('uses magnitude when provided', () => {
    expect(classifySeverity('quake', 'natural_disaster', 7.2)).toBe('critical');
    expect(classifySeverity('quake', 'natural_disaster', 6.1)).toBe('high');
    expect(classifySeverity('quake', 'natural_disaster', 4.8)).toBe('medium');
    expect(classifySeverity('quake', 'natural_disaster', 3.1)).toBe('low');
  });

  it('reads critical and high lexicons', () => {
    expect(classifySeverity('Country declares war on neighbour', 'conflict')).toBe('critical');
    expect(classifySeverity('Major escalation reported', 'diplomatic')).toBe('high');
  });

  it('gives high-baseline types a floor', () => {
    expect(classifySeverity('Talks continue', 'conflict')).toBe('high');
    expect(classifySeverity('Routine meeting', 'diplomatic')).toBe('low');
  });

  it('orders severity ranks', () => {
    expect(SEVERITY_RANK.critical).toBeGreaterThan(SEVERITY_RANK.high);
    expect(SEVERITY_RANK.high).toBeGreaterThan(SEVERITY_RANK.medium);
    expect(SEVERITY_RANK.medium).toBeGreaterThan(SEVERITY_RANK.low);
  });
});

describe('classification of channels / commodities / sectors', () => {
  it('maps channels from keywords', () => {
    expect(classifyChannels('Red sea shipping disruption raises freight costs')).toContain('Shipping & Logistics');
    expect(classifyChannels('Semiconductor export controls')).toContain('Semiconductors');
    expect(classifyChannels('nothing relevant here')).toEqual([]);
  });

  it('maps commodities', () => {
    expect(classifyCommodities('crude oil surges')).toContain('Crude Oil');
    expect(classifyCommodities('gold hits record')).toContain('Gold');
  });

  it('maps sectors', () => {
    expect(classifySectors('bank shares fall')).toContain('Financials');
    expect(classifySectors('mining output rises')).toContain('Materials');
  });
});

describe('severityWeight', () => {
  it('is monotonic and bounded', () => {
    expect(severityWeight('critical')).toBe(1);
    expect(severityWeight('low')).toBeGreaterThan(0);
    expect(severityWeight('critical')).toBeGreaterThan(severityWeight('high'));
  });
});
