'use client';

// The presentational sign-in panel: ONE frosted-glass card that shows setup,
// login, the session check, or an explicit operator misconfiguration message.
// The stateful logic (fetch + submit) lives in `login-form.tsx`, so every state
// here is server-renderable and unit-tested without a DOM.

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ShieldCheck } from '@/lib/icons';

export type AuthMode = 'checking' | 'setup' | 'login' | 'misconfigured';

export interface AuthPanelProps {
  mode: AuthMode;
  error?: string | null;
  busy?: boolean;
  onSubmit?: (username: string, password: string) => void;
}

const COPY: Record<AuthMode, { title: string; body: string; cta: string }> = {
  checking: {
    title: 'Checking your session',
    body: 'Verifying the sign-in state of this instance…',
    cta: '',
  },
  setup: {
    title: 'Create your operator account',
    body: 'This instance requires a sign-in. No account exists yet, so create the first one — it is stored only on this machine.',
    cta: 'Create account',
  },
  login: {
    title: 'Sign in',
    body: 'This instance requires a signed-in user.',
    cta: 'Sign in',
  },
  misconfigured: {
    title: 'Sign-in is required but not configured',
    body: 'Set HARNESS_AUTH_SECRET (at least 16 characters) in the environment and restart the app. Every request fails closed until then — see docs/DEPLOYMENT.md.',
    cta: '',
  },
};

export function AuthPanel({ mode, error, busy = false, onSubmit }: AuthPanelProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const copy = COPY[mode];
  const formMode = mode === 'setup' || mode === 'login';

  const inputClass =
    'w-full rounded-xl border border-border/60 bg-background/60 px-3 py-2 text-sm outline-none transition-colors focus:border-primary/60 focus:ring-2 focus:ring-primary/25';

  return (
    <div className="glass-card w-full max-w-md rounded-3xl p-8" data-auth-mode={mode}>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15">
          <ShieldCheck className="h-5 w-5 text-primary" />
        </div>
        <div>
          <div className="font-serif text-lg font-semibold tracking-tight">BlackEclipse</div>
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Operator access</div>
        </div>
      </div>

      <h1 className="text-base font-semibold">{copy.title}</h1>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{copy.body}</p>

      {mode === 'checking' && (
        <div className="mt-6 h-1 w-full overflow-hidden rounded-full bg-accent/40">
          <div className="h-full w-1/3 animate-pulse rounded-full bg-primary/70" />
        </div>
      )}

      {formMode && (
        <form
          className="mt-6 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!busy) onSubmit?.(username, password);
          }}
        >
          <label className="block text-xs">
            <span className="mb-1.5 block font-medium text-muted-foreground">Username</span>
            <input
              className={inputClass}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              required
            />
          </label>
          <label className="block text-xs">
            <span className="mb-1.5 block font-medium text-muted-foreground">Password</span>
            <input
              className={inputClass}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === 'setup' ? 'new-password' : 'current-password'}
              minLength={mode === 'setup' ? 8 : undefined}
              required
            />
          </label>
          {mode === 'setup' && (
            <p className="text-[11px] text-muted-foreground">
              At least 8 characters. The account is local to this machine; you can change it later from Settings.
            </p>
          )}
          {error && (
            <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" size="lg" className="w-full" disabled={busy}>
            {busy ? 'Working…' : copy.cta}
          </Button>
        </form>
      )}

      {mode === 'misconfigured' && error && (
        <p className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-400" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
