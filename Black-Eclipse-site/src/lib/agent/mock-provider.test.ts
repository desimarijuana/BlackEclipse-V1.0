import { describe, it, expect } from 'vitest';
import { MockProvider } from './mock-provider';

describe('MockProvider', () => {
  const provider = new MockProvider();

  it('is always configured', () => {
    expect(provider.isConfigured()).toBe(true);
  });

  it('has an id and label', () => {
    expect(provider.id).toBe('mock');
    expect(provider.label).toContain('Mock');
  });

  it('returns a research-flavored reply for analyze/research queries', async () => {
    const reply = await provider.chat([{ role: 'user', content: 'Analyze AAPL' }]);
    expect(reply.toLowerCase()).toContain('analyzing');
  });

  it('returns a sentiment reply for sentiment queries', async () => {
    const reply = await provider.chat([{ role: 'user', content: 'What is the market sentiment?' }]);
    expect(reply.toLowerCase()).toContain('bullish');
  });

  it('returns a portfolio reply for portfolio queries', async () => {
    const reply = await provider.chat([{ role: 'user', content: 'How is my portfolio doing?' }]);
    expect(reply.toLowerCase()).toContain('portfolio');
  });

  it('returns a generic reply for other queries', async () => {
    const reply = await provider.chat([{ role: 'user', content: 'hello there' }]);
    expect(reply.length).toBeGreaterThan(0);
  });
});
