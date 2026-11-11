'use client';

// Registers the offline fallback worker (`public/sw.js`).
//
// The worker is what lets a stopped Eclipse show ITS OWN "offline" page instead
// of the browser's `ERR_CONNECTION_REFUSED` screen: it answers a failed page
// navigation from its cache. That only works if it was registered during an
// earlier, successful load — so this mounts with the app shell and registers
// once, after the page has painted (never competing with the boot graph).
//
// No UI, no state. Registration failures are expected on plain `http://`
// origins other than localhost (a service worker needs a secure context: https
// or loopback) and are ignored.

import { useEffect } from 'react';

export function OfflineReady() {
  useEffect(() => {
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
    if (typeof window === 'undefined' || !window.isSecureContext) return;

    const register = () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {
        // Unsupported or blocked (private mode, policy). The app is unaffected.
      });
    };

    if (document.readyState === 'complete') register();
    else {
      window.addEventListener('load', register, { once: true });
      return () => window.removeEventListener('load', register);
    }
  }, []);

  return null;
}
