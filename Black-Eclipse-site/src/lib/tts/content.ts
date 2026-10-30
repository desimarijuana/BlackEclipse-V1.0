// ── Reply → speakable prose ─────────────────────────────────────────────────
// Chat turns may contain an `eclipse-response` fence (structured JSON). Read
// aloud, that JSON is noise — so structured turns are projected to Markdown
// with the SAME projector the copy button and PDF export use, then flattened
// to prose. Plain Markdown takes the synchronous path; only structured replies
// pull in the projection module (and its Zod contract) on demand.

import { hasResponseFence } from '@/lib/response/fence-check';
import { toSpeakableText } from './text';

/**
 * Resolve a reply's speakable text. Async only for structured responses; the
 * plain-Markdown path completes synchronously before its first await so a
 * click handler can still speak inside the user gesture (iOS requirement).
 */
export async function speakableText(content: string): Promise<string> {
  if (!content.trim()) return '';
  if (!hasResponseFence(content)) return toSpeakableText(content);
  const { projectContentMarkdown } = await import('@/lib/response/projection');
  return toSpeakableText(projectContentMarkdown(content));
}
