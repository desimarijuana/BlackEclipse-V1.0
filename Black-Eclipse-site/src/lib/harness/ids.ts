// Run id generation on the Next.js side. The Python runtime accepts the id the
// front door supplies, so both sides agree on the identifier.

import { randomUUID } from "crypto";

export function newRunId(): string {
  return `run_${randomUUID()}`;
}
