import { describe, expect, it } from 'vitest';
import { providerLogoAsset, providerLogoId } from './logo';

describe('providerLogoId', () => {
  it('resolves runtime provider ids', () => {
    expect(providerLogoId('openai')).toBe('openai');
    expect(providerLogoId('ollama')).toBe('ollama');
    expect(providerLogoId('lmstudio')).toBe('lmstudio');
  });

  it('resolves display labels with qualifiers and spacing', () => {
    expect(providerLogoId('Ollama (local)')).toBe('ollama');
    expect(providerLogoId('Google Gemini')).toBe('google');
    expect(providerLogoId('Mistral AI')).toBe('mistral');
    expect(providerLogoId('xAI Grok')).toBe('xai');
    expect(providerLogoId('Eclipse Agent')).toBe('eclipse');
  });

  it('maps known aliases', () => {
    expect(providerLogoId('gemini')).toBe('google');
    expect(providerLogoId('grok')).toBe('xai');
    expect(providerLogoId('opencode zen')).toBe('opencode');
    expect(providerLogoId('opencode-go')).toBe('opencode');
    expect(providerLogoId('ollama-cloud')).toBe('ollama');
  });

  it('never invents a brand for custom/auto/unknown providers', () => {
    expect(providerLogoId('custom')).toBeNull();
    expect(providerLogoId('auto')).toBeNull();
    expect(providerLogoId('mock')).toBeNull();
    expect(providerLogoId('some-new-provider')).toBeNull();
    expect(providerLogoId('')).toBeNull();
    expect(providerLogoId(null)).toBeNull();
  });

  it('returns a local asset path, never a remote URL', () => {
    const asset = providerLogoAsset('openai');
    expect(asset).toMatch(/^\/providers\/.+\.svg$/);
  });
});
