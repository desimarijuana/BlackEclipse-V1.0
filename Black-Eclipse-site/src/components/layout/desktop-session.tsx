"use client";

// Reports this tab's life to the desktop launcher when the app was opened from
// the desktop shortcut (?desktop=1). The launcher watches the beacon file and
// stops the dev server a few seconds after the tab closes, so the user never
// has to hunt for a background process.
//
// A period heartbeat covers browsers that skip pagehide (crash, force-quit);
// the pagehide beacon makes normal tab-close detection immediate. A reload
// re-sends "alive" within the launcher's grace window, so it does not stop the
// server.

import { useEffect } from "react";

const KEY = "be_desktop_session";

function beacon(event: "alive" | "leave") {
  const url = `/api/desktop/session?event=${event}`;
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

    beacon("alive");
    const timer = window.setInterval(() => beacon("alive"), 10_000);
    const onLeave = () => beacon("leave");
    const onShow = () => beacon("alive");
    window.addEventListener("pagehide", onLeave);
    window.addEventListener("pageshow", onShow);

    return () => {
      window.clearInterval(timer);
      window.removeEventListener("pagehide", onLeave);
      window.removeEventListener("pageshow", onShow);
    };
  }, []);

  return null;
}
