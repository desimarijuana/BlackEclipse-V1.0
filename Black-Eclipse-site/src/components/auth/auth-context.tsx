'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { authClient } from '@/lib/auth-client';

export interface UserSession {
  id: string;
  name?: string | null;
  email: string;
  image?: string | null;
  role?: string | null;
}

interface AuthContextType {
  user: UserSession | null;
  loading: boolean;
  loginDemo: () => Promise<boolean>;
  loginWithCredentials: (email: string, pass: string) => Promise<{ success: boolean; error?: string }>;
  signUpWithCredentials: (name: string, email: string, pass: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
  requireAuth: (callback: () => void) => void;
  showAuthModal: boolean;
  setShowAuthModal: (show: boolean) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);

  // Sync session on mount
  useEffect(() => {
    async function syncSession() {
      try {
        // Try getting better-auth session first
        const sessionRes = await authClient.getSession();
        if (sessionRes?.data?.user) {
          const u = sessionRes.data.user;
          setUser({ id: u.id, name: u.name, email: u.email, image: u.image, role: (u as { role?: string }).role });
        } else {
          // Check local storage fallback for demo
          const savedSession = localStorage.getItem('be_mock_session');
          if (savedSession) {
            setUser(JSON.parse(savedSession));
          }
        }
      } catch (err) {
        console.error('Session sync error:', err);
        // Robust fallback
        const savedSession = localStorage.getItem('be_mock_session');
        if (savedSession) {
          setUser(JSON.parse(savedSession));
        }
      } finally {
        setLoading(false);
      }
    }
    syncSession();
  }, []);

  const loginDemo = async () => {
    setLoading(true);
    try {
      const mockUser = {
        id: 'demo-user-id',
        name: 'Demo Researcher',
        email: 'test@blackeclipse.ai',
        image: null,
      };
      localStorage.setItem('be_mock_session', JSON.stringify(mockUser));
      setUser(mockUser);
      setShowAuthModal(false);
      if (pendingAction) {
        pendingAction();
        setPendingAction(null);
      }
      return true;
    } catch (e) {
      console.error(e);
      return false;
    } finally {
      setLoading(false);
    }
  };

  const loginWithCredentials = async (email: string, pass: string) => {
    setLoading(true);
    try {
      // Direct demo intercept for test email/pass
      if (email.toLowerCase() === 'test@blackeclipse.ai' && pass === 'password123') {
        const mockUser = {
          id: 'demo-user-id',
          name: 'Demo Researcher',
          email: 'test@blackeclipse.ai',
          image: null,
          role: null,
        };
        localStorage.setItem('be_mock_session', JSON.stringify(mockUser));
        setUser(mockUser);
        setShowAuthModal(false);
        if (pendingAction) {
          pendingAction();
          setPendingAction(null);
        }
        return { success: true };
      }

      // Try better-auth login
      const { data, error } = await authClient.signIn.email({ email, password: pass });
      if (error) {
        throw new Error(error.message ?? 'Authentication failed');
      }

      if (data?.user) {
        const u = data.user;
        // Extract role — better-auth returns it in the user object
        const role = (u as { role?: string }).role || null;
        const mappedUser = { id: u.id, name: u.name, email: u.email, image: u.image, role };
        setUser(mappedUser);
        // Save to localStorage including role so it persists on refresh
        localStorage.setItem('be_mock_session', JSON.stringify(mappedUser));
      } else {
        // Fallback for custom user creation mock if not fully seeded
        const fallbackUser = { id: 'user-' + Date.now(), name: email.split('@')[0], email, role: null };
        setUser(fallbackUser);
        localStorage.setItem('be_mock_session', JSON.stringify(fallbackUser));
      }

      setShowAuthModal(false);
      if (pendingAction) {
        pendingAction();
        setPendingAction(null);
      }
      return { success: true };
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Login failed';
      return { success: false, error: errMsg };
    } finally {
      setLoading(false);
    }
  };

  const signUpWithCredentials = async (name: string, email: string, pass: string) => {
    setLoading(true);
    try {
      // Simulate/Trigger sign up
      const { data, error } = await authClient.signUp.email({ name, email, password: pass });
      if (error) {
        throw new Error(error.message ?? 'Registration failed');
      }

      const newUser = {
        id: data?.user?.id || 'user-' + Date.now(),
        name,
        email,
        image: null
      };

      setUser(newUser);
      localStorage.setItem('be_mock_session', JSON.stringify(newUser));
      setShowAuthModal(false);
      if (pendingAction) {
        pendingAction();
        setPendingAction(null);
      }
      return { success: true };
    } catch (err) {
      // For development, if backend db is not set up / prisma offline, mock sign up success
      console.warn('Backend sign up warning, falling back to mock registration:', err);
      const mockUser = { id: 'mock-' + Date.now(), name, email, image: null };
      setUser(mockUser);
      localStorage.setItem('be_mock_session', JSON.stringify(mockUser));
      setShowAuthModal(false);
      if (pendingAction) {
        pendingAction();
        setPendingAction(null);
      }
      return { success: true };
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    try {
      await authClient.signOut();
    } catch (e) {
      console.warn('Better auth logout error, clearing local cache:', e);
    }
    localStorage.removeItem('be_mock_session');
    setUser(null);
  };

  const requireAuth = (callback: () => void) => {
    if (user) {
      callback();
    } else {
      setPendingAction(() => callback);
      setShowAuthModal(true);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        loginDemo,
        loginWithCredentials,
        signUpWithCredentials,
        logout,
        requireAuth,
        showAuthModal,
        setShowAuthModal,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
