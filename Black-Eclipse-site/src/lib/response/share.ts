// ── Figure deep-link (share/embed) ───────────────────────────────────────────
//
// A `model3d` (or any response block) can be shared as a self-contained URL:
// the block is serialized, UTF-8 encoded and base64url'd into the URL hash, and
// `/figure` decodes it and renders it standalone. No server storage, no account.

import { parseResponsePayload, type ParsedResponse } from '@/lib/response/contract';

function toBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]!);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function fromBase64(text: string): Uint8Array {
  const padded = text.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** A URL hash carrying one block, safe for a query-free hash (no `+`/`/`/`=`). */
export function encodeFigure(block: unknown): string {
  const json = JSON.stringify({ blocks: [block] });
  return toBase64(new TextEncoder().encode(json));
}

/** The absolute share URL for a block, for the current origin. */
export function figureUrl(block: unknown, origin: string): string {
  return `${origin.replace(/\/$/, '')}/figure#${encodeFigure(block)}`;
}

/** Decode a `/figure#…` hash back into a parsed response, or null when invalid. */
export function decodeFigure(hash: string): ParsedResponse | null {
  try {
    const clean = hash.replace(/^#/, '');
    if (!clean) return null;
    const payload = JSON.parse(new TextDecoder().decode(fromBase64(clean)));
    return parseResponsePayload(payload);
  } catch {
    return null;
  }
}
