import { describe, it, expect } from 'vitest';
import { classifyIntent, extractSymbol } from './intent';

describe('classifyIntent', () => {
  it('detects action verbs', () => {
    expect(classifyIntent('go to portfolio').intent).toBe('action');
    expect(classifyIntent('open journal').intent).toBe('action');
    expect(classifyIntent('add aapl to watchlist').intent).toBe('action');
  });

  it('detects indicator keywords', () => {
    expect(classifyIntent('NFP').intent).toBe('indicator');
    expect(classifyIntent('us jobs data').intent).toBe('indicator');
    expect(classifyIntent('CPI').intent).toBe('indicator');
  });

  it('detects event queries', () => {
    expect(classifyIntent('economic events today').intent).toBe('event');
    expect(classifyIntent('next NFP').intent).toBe('event');
  });

  it('detects user-owned data', () => {
    expect(classifyIntent('my trades').intent).toBe('user');
    expect(classifyIntent('winning trades').intent).toBe('user');
  });

  it('detects sentence-like AI questions', () => {
    expect(classifyIntent('What economic data should I watch before NFP?').intent).toBe('ai');
  });

  it('falls back to entity for plain terms', () => {
    expect(classifyIntent('aapl').intent).toBe('entity');
    expect(classifyIntent('bitcoin').intent).toBe('entity');
  });
});

describe('extractSymbol', () => {
  it('extracts a ticker token', () => {
    expect(extractSymbol('aapl price')).toBe('AAPL');
    expect(extractSymbol('nvda earnings')).toBe('NVDA');
  });

  it('returns undefined for plain words', () => {
    expect(extractSymbol('my portfolio')).toBeUndefined();
  });
});
