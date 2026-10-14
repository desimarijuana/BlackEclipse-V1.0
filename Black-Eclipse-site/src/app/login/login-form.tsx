'use client';

// The sign-in page's stateful half: resolve whether this instance needs setup or
// a sign-in (via `/api/auth/me`), submit credentials, then return the user to
// the path the middleware remembered (`?next=`, sanitized by `safeNext`).

import { useEffect, useState } from 'react';
import { AuthPanel, type AuthMode } from './auth-panel';
import { safeNext } from './next-path';

async function postJson(url: string, body: unknown): Promise<{ ok: boolean; data: Record<string, unknown> }> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  return { ok: res.ok, data };
}

export function LoginForm() {
  const [mode, setMode] = useState<AuthMode>('checking');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const next = safeNext(new URLSearchParams(window.location.search).get('next'));
    (async () => {
      try {
        const res = await fetch('/api/auth/me');
        const data = (await res.json()) as {
          authRequired?: boolean;
          authenticated?: boolean;
          configured?: boolean;
          setupRequired?: boolean;
        };
        if (cancelled) return;
        // Authentication is off (the zero-config local case): nothing to do here.
        if (!data.authRequired) {
          window.location.replace(next);
          return;
        }
        if (data.authenticated) {
          window.location.replace(next);
          return;
        }
        if (data.configured === false) {
          setMode('misconfigured');
          return;
        }
        setMode(data.setupRequired ? 'setup' : 'login');
      } catch {
        if (!cancelled) {
          setMode('login');
          setError('Could not reach the server. Retry in a moment.');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = async (username: string, password: string) => {
    setBusy(true);
    setError(null);
    const next = safeNext(new URLSearchParams(window.location.search).get('next'));
    try {
      if (mode === 'setup') {
        const created = await postJson('/api/auth/setup', { username, password });
        if (!created.ok) {
          setError(String(created.data.error ?? 'Could not create the account.'));
          return;
        }
        // Setup creates the account but does not sign in; use it once now.
        const signedIn = await postJson('/api/auth/login', { username, password });
        if (!signedIn.ok) {
          setMode('login');
          setError('Account created — sign in with your new credentials.');
          return;
        }
        window.location.replace(next);
        return;
      }
      const signedIn = await postJson('/api/auth/login', { username, password });
      if (!signedIn.ok) {
        setError(String(signedIn.data.error ?? 'Incorrect username or password.'));
        return;
      }
      window.location.replace(next);
    } catch {
      setError('Could not reach the server. Retry in a moment.');
    } finally {
      setBusy(false);
    }
  };

  return <AuthPanel mode={mode} error={error} busy={busy} onSubmit={submit} />;
}
