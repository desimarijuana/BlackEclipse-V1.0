// Sign-in / first-run setup — the UI behind the `HARNESS_AUTH=required` gate
// (see docs/harness/authentication.md). A STANDALONE page outside the app shell
// (the middleware allows it without a session so a user can authenticate).
// Server shell; the interactive half lives in `login-form.tsx`.
import type { Metadata } from 'next';
import { LoginForm } from './login-form';

export const metadata: Metadata = {
  title: 'Sign in — BlackEclipse',
  description: 'Sign in to BlackEclipse (or create the first operator account on a new instance).',
};

export default function LoginPage() {
  return (
    <div className="app-page-bg flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
      <LoginForm />
    </div>
  );
}
