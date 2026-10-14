import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AuthPanel } from './auth-panel';

// Server-rendered state coverage for the sign-in page (the interactive fetch
// path is exercised end-to-end against a real production server in the release
// smoke; here we pin every state's markup, including the fail-closed one).

describe('AuthPanel', () => {
  it('renders the setup form when no account exists', () => {
    const html = renderToStaticMarkup(<AuthPanel mode="setup" />);
    expect(html).toContain('Create your operator account');
    expect(html).toContain('Create account');
    expect(html).toContain('type="password"');
    expect(html).toContain('data-auth-mode="setup"');
  });

  it('renders the sign-in form and any error otherwise', () => {
    const html = renderToStaticMarkup(<AuthPanel mode="login" error="Incorrect username or password." />);
    expect(html).toContain('Sign in');
    expect(html).toContain('Incorrect username or password.');
    expect(html).toContain('type="password"');
  });

  it('fails closed with operator guidance when the secret is missing (no form)', () => {
    const html = renderToStaticMarkup(<AuthPanel mode="misconfigured" />);
    expect(html).toContain('HARNESS_AUTH_SECRET');
    expect(html).not.toContain('type="password"');
  });

  it('shows the session check without a form', () => {
    const html = renderToStaticMarkup(<AuthPanel mode="checking" />);
    expect(html).toContain('Checking your session');
    expect(html).not.toContain('type="password"');
  });
});
