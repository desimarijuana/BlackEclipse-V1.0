"use client";

// The login / first-run setup screen.
//
// It is intentionally minimal and self-contained: it talks only to
// `/api/auth/*`, so it works whether the app is in single-user local mode (it is
// normally not reached) or multi-user mode. On success it hard-navigates to the
// `next` return path so a fresh session cookie is sent with the request.

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

type Mode = "loading" | "login" | "setup";

// `useSearchParams` requires a Suspense boundary during static generation, so
// the form is wrapped below. The fallback matches the page's dark shell.
function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const nextPath = params.get("next") || "/";

  const [mode, setMode] = useState<Mode>("loading");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/auth/me", { cache: "no-store" });
        const body = await res.json();
        if (cancelled) return;
        if (body.authenticated) {
          router.replace(nextPath);
          return;
        }
        // If no account exists yet, show first-run setup instead of login.
        setMode(body.setupRequired ? "setup" : "login");
      } catch {
        if (!cancelled) setMode("login");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router, nextPath]);

  const submit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      setError(null);
      if (mode === "setup" && password !== confirm) {
        setError("The two passwords do not match.");
        return;
      }
      setBusy(true);
      try {
        const endpoint = mode === "setup" ? "/api/auth/setup" : "/api/auth/login";
        const res = await fetch(endpoint, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ username, password }),
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          setError(typeof body.error === "string" ? body.error : "Sign-in failed.");
          setBusy(false);
          return;
        }
        // Setup creates the account but does not sign in; go through login.
        if (mode === "setup") {
          const login = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ username, password }),
          });
          if (!login.ok) {
            setMode("login");
            setError("Account created. Please sign in.");
            setBusy(false);
            return;
          }
        }
        window.location.assign(nextPath);
      } catch {
        setError("Sign-in failed. Is the server running?");
        setBusy(false);
      }
    },
    [mode, username, password, confirm, nextPath]
  );

  return (
    <main className="flex min-h-screen items-center justify-center bg-black p-6">
      <form
        onSubmit={submit}
        className="glass-card-strong w-full max-w-sm rounded-2xl p-8 text-zinc-100"
      >
        <h1 className="text-xl font-semibold tracking-tight">BlackEclipse</h1>
        <p className="mt-1 text-sm text-zinc-400">
          {mode === "setup" ? "Create the operator account for this deployment." : "Sign in to continue."}
        </p>

        <label className="mt-6 block text-xs uppercase tracking-wide text-zinc-400" htmlFor="username">
          Username
        </label>
        <input
          id="username"
          value={username}
          autoComplete="username"
          onChange={(e) => setUsername(e.target.value)}
          className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-white/25"
        />

        <label className="mt-4 block text-xs uppercase tracking-wide text-zinc-400" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          type="password"
          value={password}
          autoComplete={mode === "setup" ? "new-password" : "current-password"}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-white/25"
        />

        {mode === "setup" && (
          <>
            <label className="mt-4 block text-xs uppercase tracking-wide text-zinc-400" htmlFor="confirm">
              Confirm password
            </label>
            <input
              id="confirm"
              type="password"
              value={confirm}
              autoComplete="new-password"
              onChange={(e) => setConfirm(e.target.value)}
              className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-white/25"
            />
          </>
        )}

        {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={busy || mode === "loading"}
          className="mt-6 w-full rounded-lg bg-white/90 px-4 py-2 text-sm font-medium text-black transition hover:bg-white disabled:opacity-50"
        >
          {busy ? "Working…" : mode === "setup" ? "Create account" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-black p-6">
          <div className="glass-card-strong w-full max-w-sm rounded-2xl p-8 text-center text-sm text-zinc-400">
            Loading…
          </div>
        </main>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
