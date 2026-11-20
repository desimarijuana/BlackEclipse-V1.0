// ── Custom connection auth vocabulary (client-safe) ─────────────────────────
// Kept free of server imports so the connect UI and the runtime/probe code can
// share one definition of how a custom gateway expects its key.

export type CustomAuthStyle = "bearer" | "x-api-key" | "api-key" | "header";

export const CUSTOM_AUTH_STYLES: Array<{
  value: CustomAuthStyle;
  label: string;
  hint: string;
}> = [
  { value: "bearer", label: "Bearer token", hint: "Authorization: Bearer <key>" },
  { value: "x-api-key", label: "x-api-key header", hint: "x-api-key: <key>" },
  { value: "api-key", label: "api-key header", hint: "api-key: <key> (Azure-style gateways)" },
  { value: "header", label: "Custom header", hint: "Your own header name and optional prefix" },
];

export function authForConnection(connection: {
  authStyle: CustomAuthStyle;
  apiKeyHeader?: string;
  apiKeyPrefix?: string;
}): { header: string; prefix: string } {
  switch (connection.authStyle) {
    case "x-api-key":
      return { header: "x-api-key", prefix: connection.apiKeyPrefix ?? "" };
    case "api-key":
      return { header: "api-key", prefix: connection.apiKeyPrefix ?? "" };
    case "header":
      return {
        header: (connection.apiKeyHeader ?? "authorization").trim() || "authorization",
        prefix: connection.apiKeyPrefix ?? "",
      };
    case "bearer":
    default:
      return { header: "authorization", prefix: "Bearer " };
  }
}
