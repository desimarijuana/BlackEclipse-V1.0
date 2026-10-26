'use client';

// The structured-response rendering path, split out of `chat-history.tsx` so the
// response engine (Zod contract, block registry, planners, Mermaid/model3d
// blocks) is downloaded only when the first assistant turn actually renders —
// not on the chat shell's first paint.

import { memo, useMemo } from 'react';
import { Markdown } from './markdown';
import { ResponseView } from '@/components/response/response-view';
import { hasResponseFence } from '@/lib/response/fence-check';
import { planMarkdown, plannerUpgraded } from '@/lib/response/planner';

/** A model-authored app fence — Markdown must own it so it renders live. */
const APP_FENCE = /(^|\n)\s*```(?:html|htm|xhtml|svg|eclipse-app)\b/i;

/**
 * Assistant prose is the expensive part to render (full Markdown parse). It only
 * changes when its text does, so memoizing it stops a streaming turn from
 * re-parsing every *other* turn in the transcript.
 *
 * When a settled answer contains a structured response fence, `Markdown` renders
 * it inline. When it does not, the deterministic planner re-presents plain
 * Markdown (tables → interactive tables, source lists → citations) without
 * changing the words. While streaming, it falls back to raw Markdown so a
 * half-written block never flickers into a structured render.
 */
export const AssistantContent = memo(function AssistantContent({
  content,
  compact,
  streaming,
  onFollowup,
}: {
  content: string;
  compact: boolean;
  streaming: boolean;
  onFollowup?: (prompt: string) => void;
}) {
  const planned = useMemo(() => {
    if (streaming || hasResponseFence(content) || APP_FENCE.test(content)) return null;
    const response = planMarkdown(content);
    return plannerUpgraded(response) ? response : null;
  }, [content, streaming]);

  if (planned) {
    return <ResponseView response={planned} compact={compact} onFollowup={onFollowup} />;
  }
  return <Markdown content={content} compact={compact} streaming={streaming} onFollowup={onFollowup} className="w-full" />;
});
