"use client";

// ── Settings prefetch ────────────────────────────────────────────────────────
// Warm the Settings modal without putting it on the boot path:
//   * the data snapshot is fetched shortly after first paint (cheap JSON),
//   * the lazily-loaded modal chunk is warmed on gear hover/focus (intent) and
//     again after the first screen has settled, so a click never waits.
// Delayed and skipped on metered connections so it cannot compete with boot.

import { useCallback, useEffect } from "react";
import { prefetchSettingsData } from "@/lib/settings-cache";

const CHUNK_WARM_MS = 12000;

export function useSettingsPrefetch(): () => void {
  const prefetch = useCallback(() => {
    void prefetchSettingsData();
    void import("@/components/screens/settings");
  }, []);

  useEffect(() => {
    const dataTimer = setTimeout(() => {
      void prefetchSettingsData();
    }, 2500);
    const chunkTimer = setTimeout(() => {
      const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
      if (!connection?.saveData) void import("@/components/screens/settings");
    }, CHUNK_WARM_MS);
    return () => {
      clearTimeout(dataTimer);
      clearTimeout(chunkTimer);
    };
  }, []);

  return prefetch;
}
