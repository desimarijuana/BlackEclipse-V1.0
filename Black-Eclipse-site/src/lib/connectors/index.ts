// ── Connector layer entry point ─────────────────────────────────────────────
// Registers the built-in connectors exactly once, then re-exports the public
// surface used by API routes and other server code.
//
// Server-only: the runtime performs outbound requests and decrypts credentials.

import { registerBuiltinConnectors } from "./builtins";

registerBuiltinConnectors();

export { registerBuiltinConnectors, resetBuiltinRegistration } from "./builtins";
export * from "./types";
export * from "./registry";
export * from "./resolver";
export * from "./runtime";
export * from "./health";
export * from "./mapping";
export * from "./custom-rest";
export * from "./security";
export * from "./refresh";
export { cryptoConnector, CRYPTO_CONNECTOR_ID, parseBinanceTicker, toBinancePair } from "./providers/crypto";
