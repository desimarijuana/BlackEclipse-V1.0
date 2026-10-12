'use client';

import { useEffect, useState } from 'react';

/**
 * True while the app is in dark mode. The app switches scheme by toggling the
 * `dark` class on `<html>` (see `lib/chart/providers/eclipse-provider.ts`), so
 * this observes that one signal and re-renders on change. This is the shared
 * source of truth for any DOM/SVG/canvas code that cannot read Tailwind tokens.
 */
export function useDarkScheme(defaultValue = true): boolean {
  const [isDark, setIsDark] = useState(defaultValue);
  useEffect(() => {
    const root = document.documentElement;
    const read = () => setIsDark(root.classList.contains('dark'));
    read();
    const observer = new MutationObserver(read);
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);
  return isDark;
}
