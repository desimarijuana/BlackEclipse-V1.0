"use client";

// Reports this tab's life to the desktop launcher when the app was opened from
// the desktop shortcut (?desktop=1). The launcher watches the beacon file and
// stops the server a few seconds after the LAST tab closes, so the user never
// has to hunt for a background process.
//
// Every page load sends its own tab id: the beacon file is a refcount, so
// closing one of several open tabs (or a duplicate tab, which inherits
// sessionStorage) cannot stop the server under the others.
//
// A periodic heartbeat covers browsers that skip pagehide (crash, force-quit);
// the pagehide beacon makes normal tab-close detection immediate. A reload
// re-sends "alive" within the launcher's grace window, so it does not stop the
// server. visibilitychange/pageshow re-report a tab that was frozen/throttled
// in the background or resumed after the machine slept.

import { useEffect } from "react";

const KEY = "be_desktop_session";
const HEARTBEAT_MS = 10_000;

function newTabId() {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID().replace(/-/g, "");
    }
  } catch {
    /* fall through */
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function beacon(tabId: string, event: "alive" | "leave") {
  const url = `/api/desktop/session?event=${event}&tab=${encodeURIComponent(tabId)}`;
  if (event === "leave" && typeof navigator.sendBeacon === "function") {
    navigator.sendBeacon(url);
    return;
  }
  void fetch(url, { method: "POST", keepalive: true }).catch(() => {});
}

export function DesktopSession() {
  useEffect(() => {
    let enabled = false;
    try {
      const query = new URLSearchParams(window.location.search);
      if (query.get("desktop") === "1") {
        sessionStorage.setItem(KEY, "1");
        query.delete("desktop");
        const rest = query.toString();
        window.history.replaceState(null, "", window.location.pathname + (rest ? `?${rest}` : "") + window.location.hash);
      }
      enabled = sessionStorage.getItem(KEY) === "1";
    } catch {
      enabled = false;
    }
    if (!enabled) return;

    // Per page load, NOT persisted: a duplicated tab copies sessionStorage, and
    // two tabs sharing one id would let closing either one end the session.
    const tabId = newTabId();
    beacon(tabId, "alive");

    const timer = window.setInterval(() => beacon(tabId, "alive"), HEARTBEAT_MS);
    const onLeave = () => beacon(tabId, "leave");
    const onShow = () => beacon(tabId, "alive");
    const onVisibility = () => {
      if (document.visibilityState === "visible") beacon(tabId, "alive");
    };
    window.addEventListener("pagehide", onLeave);
    window.addEventListener("pageshow", onShow);
    window.addEventListener("focus", onShow);
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      window.clearInterval(timer);
      window.removeEventListener("pagehide", onLeave);
      window.removeEventListener("pageshow", onShow);
      window.removeEventListener("focus", onShow);
      document.removeEventListener("visibilitychange", onVisibility);
      // React unmount (rare in the root layout) should not orphan this tab.
      beacon(tabId, "leave");
    };
  }, []);

  return null;
}
