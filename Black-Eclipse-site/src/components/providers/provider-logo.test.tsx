import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ProviderLogo } from './provider-logo';

describe('ProviderLogo', () => {
  it('renders the provider brand as a currentColor mask', () => {
    const html = renderToStaticMarkup(<ProviderLogo provider="ollama" size={14} />);
    expect(html).toContain('/providers/ollama.svg');
    expect(html).toContain('mask-image');
    expect(html).toContain('bg-current');
  });

  it('renders a neutral glyph for a provider with no brand', () => {
    const html = renderToStaticMarkup(<ProviderLogo provider="custom" />);
    expect(html).not.toContain('/providers/');
    expect(html).toContain('<svg');
  });
});
