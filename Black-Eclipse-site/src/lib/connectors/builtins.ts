// ── Built-in connector registration ─────────────────────────────────────────
// Kept in its own module (rather than in the `index.ts` barrel) so consumers
// like the refresh scheduler can ensure built-ins are registered without
// pulling in — and creating a cycle with — the whole public surface.

import { registerConnector } from "./registry";
import { cryptoConnector } from "./providers/crypto";

let registered = false;

/** Register all built-in connectors (idempotent). */
export function registerBuiltinConnectors(): void {
  if (registered) return;
  registerConnector(cryptoConnector);
  registered = true;
}

/** Test seam: allow built-ins to be re-registered after a registry reset. */
export function resetBuiltinRegistration(): void {
  registered = false;
}
