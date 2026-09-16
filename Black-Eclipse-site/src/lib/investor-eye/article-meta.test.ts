import { describe, it, expect } from 'vitest';
import { extractArticleMeta, decodeEntities, isUninformativeTitle, stripSiteSuffix } from './article-meta';

describe('decodeEntities', () => {
  it('decodes named and numeric entities', () => {
    expect(decodeEntities('Oil &amp; gas')).toBe('Oil & gas');
    expect(decodeEntities('&#8217;quote&#8217;')).toBe('’quote’');
    expect(decodeEntities('caf&#233;')).toBe('café');
    expect(decodeEntities('A &#x2014; B')).toBe('A — B');
  });
  it('leaves unknown entities alone', () => {
    expect(decodeEntities('&notarealentity;')).toBe('&notarealentity;');
  });
});

describe('extractArticleMeta', () => {
  const ogPage = `<!doctype html><html><head>
    <meta property="og:title" content="Iran strikes leave port closed" />
    <meta property="og:description" content="Shipping halted after the attack." />
    <meta property="og:site_name" content="Example News" />
    <title>Fallback title</title>
  </head><body><h1>Body heading</h1></body></html>`;

  it('prefers og:title and reads the description', () => {
    const meta = extractArticleMeta(ogPage);
    expect(meta?.title).toBe('Iran strikes leave port closed');
    expect(meta?.description).toBe('Shipping halted after the attack.');
    expect(meta?.titleSource).toBe('og:title');
    expect(meta?.siteName).toBe('Example News');
  });

  it('tolerates reversed attribute order', () => {
    const html = `<head><meta content="Reversed order works" property="og:title"></head>`;
    expect(extractArticleMeta(html)?.title).toBe('Reversed order works');
  });

  it('falls back to twitter:title, then <title>, then <h1>', () => {
    expect(extractArticleMeta('<head><meta name="twitter:title" content="From twitter card"></head>')?.titleSource)
      .toBe('twitter:title');
    expect(extractArticleMeta('<head><title>From the document title tag</title></head>')?.titleSource)
      .toBe('<title>');
    expect(extractArticleMeta('<html><body><h1>From a body heading</h1></body></html>')?.titleSource)
      .toBe('<h1>');
  });

  it('ignores meta tags in the BODY (a page quoting "og:title")', () => {
    const html = `<!doctype html><html><head><title>Real title here</title></head>
      <body><p>How to write &lt;meta property="og:title" content="Fake injected title"&gt;</p></body></html>`;
    expect(extractArticleMeta(html)?.title).toBe('Real title here');
  });

  it('decodes entities and strips inline markup', () => {
    const html = '<head><meta property="og:title" content="Oil &amp; gas: <b>prices</b> surge"></head>';
    expect(extractArticleMeta(html)?.title).toBe('Oil & gas: prices surge');
  });

  it('collapses whitespace', () => {
    const html = '<head><meta property="og:title" content="Spaced    out\n\n  title"></head>';
    expect(extractArticleMeta(html)?.title).toBe('Spaced out title');
  });

  it('returns null when there is no usable title', () => {
    expect(extractArticleMeta('')).toBeNull();
    expect(extractArticleMeta('<html><head></head><body>no title at all</body></html>')).toBeNull();
  });
});

describe('isUninformativeTitle', () => {
  it('rejects bot walls and consent screens', () => {
    expect(isUninformativeTitle('Just a moment...')).toBe(true);
    expect(isUninformativeTitle('Access Denied')).toBe(true);
    expect(isUninformativeTitle('Please enable JavaScript to continue')).toBe(true);
    expect(isUninformativeTitle('404 Not Found')).toBe(true);
  });
  it('rejects a title that is just the site name', () => {
    expect(isUninformativeTitle('Example News', 'Example News')).toBe(true);
  });
  it('accepts a real headline', () => {
    expect(isUninformativeTitle('Tanker attacked in the Red Sea, crew unharmed')).toBe(false);
  });
  it('rejects very short titles', () => {
    expect(isUninformativeTitle('Home')).toBe(true);
  });
});

describe('stripSiteSuffix', () => {
  it('removes a trailing site name', () => {
    expect(stripSiteSuffix('Oil prices surge - Example News', 'Example News')).toBe('Oil prices surge');
    expect(stripSiteSuffix('Port closed | Reuters', 'Reuters')).toBe('Port closed');
  });
  it('keeps the title when stripping would leave nothing useful', () => {
    expect(stripSiteSuffix('Short - Example', 'Example')).toBe('Short - Example');
  });
  it('keeps the title when no site name is known', () => {
    expect(stripSiteSuffix('Port closed | Reuters')).toBe('Port closed | Reuters');
  });
  it('leaves a title without a suffix alone', () => {
    expect(stripSiteSuffix('A plain headline about shipping', 'Example News')).toBe('A plain headline about shipping');
  });
});
