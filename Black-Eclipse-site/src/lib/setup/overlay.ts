// ── Setup overlay marker (client-only) ─────────────────────────────────────
// The wizard is an overlay, so a forced re-run (`?setup=1`) still has the app
// shell mounted behind it. Long-lived SSE streams then compete with the
// wizard's own requests for the browser's six HTTP/1.1 connections per origin.
//
// This tiny marker lets stream owners step aside while the wizard is on screen
// and reconnect afterwards. The normal first-run path never needs it (there is
// no app shell), but a re-run must have the same headroom.

export const SETUP_OVERLAY_EVENT = "be:setup-overlay";

export function isSetupOverlayOpen(): boolean {
  return typeof document !== "undefined" && document.documentElement.dataset.beSetup === "1";
}

export function setSetupOverlay(open: boolean): void {
  if (typeof document === "undefined") return;
  if (open) document.documentElement.dataset.beSetup = "1";
  else delete document.documentElement.dataset.beSetup;
  window.dispatchEvent(new CustomEvent(SETUP_OVERLAY_EVENT, { detail: { open } }));
}

export function subscribeSetupOverlay(listener: (open: boolean) => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = (event: Event) => {
    const detail = (event as CustomEvent<{ open?: boolean }>).detail;
    listener(detail?.open === true);
  };
  window.addEventListener(SETUP_OVERLAY_EVENT, handler);
  return () => window.removeEventListener(SETUP_OVERLAY_EVENT, handler);
}
