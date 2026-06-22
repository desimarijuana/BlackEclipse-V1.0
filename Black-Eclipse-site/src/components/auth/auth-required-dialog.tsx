'use client';

import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useAuth } from './auth-context';
import { KeyRound, Lock, User, Mail, Sparkles, Loader2 } from 'lucide-react';

export function AuthRequiredDialog() {
  const {
    showAuthModal,
    setShowAuthModal,
    loginDemo,
    loginWithCredentials,
    signUpWithCredentials,
  } = useAuth();

  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleAutofillDemo = async () => {
    setLoading(true);
    setError('');
    // Wait briefly for a visual "autofill" animation
    setEmail('test@blackeclipse.ai');
    setPassword('password123');
    setTimeout(async () => {
      const success = await loginDemo();
      if (!success) {
        setError('Demo login failed');
      }
      setLoading(false);
    }, 600);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (mode === 'login') {
        const res = await loginWithCredentials(email, password);
        if (!res.success) {
          setError(res.error || 'Invalid credentials');
        }
      } else {
        if (!name.trim()) {
          setError('Name is required');
          setLoading(false);
          return;
        }
        const res = await signUpWithCredentials(name, email, password);
        if (!res.success) {
          setError(res.error || 'Registration failed');
        }
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'An error occurred';
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!loading) {
      setShowAuthModal(open);
      setError('');
    }
  };

  if (!mounted) return null;

  return (
    <Dialog open={showAuthModal} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[420px] bg-background/90 backdrop-blur-xl border border-border/40 text-foreground rounded-2xl shadow-2xl p-6 overflow-hidden">
        {/* Glow overlay inside the dialog */}
        <div className="absolute top-0 right-0 -translate-y-1/2 translate-x-1/2 w-64 h-64 bg-primary/10 rounded-full blur-[60px] pointer-events-none" />
        
        <DialogHeader className="text-center relative z-10 pt-2">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-primary/20 to-accent/20 border border-primary/20 flex items-center justify-center mx-auto mb-4 text-primary animate-pulse">
            <Lock className="w-5 h-5" />
          </div>
          <DialogTitle className="text-2xl font-semibold tracking-tight font-serif">
            {mode === 'login' ? 'Welcome to BlackEclipse' : 'Create Your Account'}
          </DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs mt-1">
            {mode === 'login'
              ? 'Sign in to access your stock research, screener dashboard, and AI analyst.'
              : 'Register to customize your portfolio, save watchlists, and unlock daily briefings.'}
          </DialogDescription>
        </DialogHeader>

        {/* Demo Mode autofill card */}
        <div className="relative z-10 p-3.5 rounded-xl border border-primary/20 bg-primary/5 shadow-inner mt-2 mb-1 group transition-all duration-300">
          <div className="flex items-start gap-2.5">
            <div className="p-1 rounded-lg bg-primary/10 text-primary mt-0.5">
              <Sparkles className="w-4 h-4" />
            </div>
            <div className="flex-1 text-left">
              <span className="text-[11px] font-semibold text-primary uppercase tracking-wide">Development & Demo Mode</span>
              <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
                Test the platform immediately. Email: <code className="text-foreground font-mono bg-accent/30 px-1 rounded">test@blackeclipse.ai</code>, Pass: <code className="text-foreground font-mono bg-accent/30 px-1 rounded">password123</code>.
              </p>
              <Button
                type="button"
                size="sm"
                onClick={handleAutofillDemo}
                disabled={loading}
                className="w-full mt-2.5 rounded-lg bg-primary hover:bg-primary/95 text-primary-foreground font-medium text-xs py-1.5 h-auto cursor-pointer"
              >
                {loading && email === 'test@blackeclipse.ai' ? (
                  <span className="flex items-center justify-center gap-1.5">
                    <Loader2 className="w-3 h-3 animate-spin" /> Logging into Demo...
                  </span>
                ) : (
                  'Autofill & Login to Demo Instantly'
                )}
              </Button>
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3.5 relative z-10 mt-2">
          {mode === 'register' && (
            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-muted-foreground tracking-wider uppercase" htmlFor="auth-name">
                Full Name
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-muted-foreground pointer-events-none">
                  <User className="w-4 h-4" />
                </span>
                <input
                  id="auth-name"
                  type="text"
                  placeholder="John Doe"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="block w-full pl-9 pr-3 py-2 bg-background/50 border border-border/40 rounded-xl text-xs placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all"
                  required
                />
              </div>
            </div>
          )}

          <div className="space-y-1">
            <label className="text-[11px] font-semibold text-muted-foreground tracking-wider uppercase" htmlFor="auth-email">
              Email Address
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-muted-foreground pointer-events-none">
                <Mail className="w-4 h-4" />
              </span>
              <input
                id="auth-email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="block w-full pl-9 pr-3 py-2 bg-background/50 border border-border/40 rounded-xl text-xs placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all"
                required
              />
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex justify-between items-center">
              <label className="text-[11px] font-semibold text-muted-foreground tracking-wider uppercase" htmlFor="auth-password">
                Password
              </label>
            </div>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-muted-foreground pointer-events-none">
                <KeyRound className="w-4 h-4" />
              </span>
              <input
                id="auth-password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="block w-full pl-9 pr-3 py-2 bg-background/50 border border-border/40 rounded-xl text-xs placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all"
                required
              />
            </div>
          </div>

          {error && (
            <div className="p-2.5 rounded-lg border border-destructive/20 bg-destructive/5 text-destructive text-[11px] font-medium leading-relaxed">
              {error}
            </div>
          )}

          <Button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-foreground hover:bg-foreground/90 text-background font-medium py-2.5 text-xs h-auto cursor-pointer"
          >
            {loading && email !== 'test@blackeclipse.ai' ? (
              <span className="flex items-center justify-center gap-1.5">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Processing...
              </span>
            ) : mode === 'login' ? (
              'Sign In to BlackEclipse'
            ) : (
              'Create Account'
            )}
          </Button>
        </form>

        <div className="relative z-10 text-center text-xs text-muted-foreground mt-4 pt-3 border-t border-border/20">
          {mode === 'login' ? (
            <p>
              New to BlackEclipse?{' '}
              <button
                type="button"
                onClick={() => {
                  setMode('register');
                  setError('');
                }}
                className="text-primary hover:underline font-semibold cursor-pointer outline-none"
              >
                Create an account
              </button>
            </p>
          ) : (
            <p>
              Already have an account?{' '}
              <button
                type="button"
                onClick={() => {
                  setMode('login');
                  setError('');
                }}
                className="text-primary hover:underline font-semibold cursor-pointer outline-none"
              >
                Sign in instead
              </button>
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
