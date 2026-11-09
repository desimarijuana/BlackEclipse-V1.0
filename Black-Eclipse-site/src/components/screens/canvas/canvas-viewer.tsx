'use client';

// ─── Canvas viewer — render chat content at reading width ────────────────────
// Read-only, framework-reusing renderers. Nothing here is a second markdown or
// block engine: markdown uses the chat renderer, reports use the response block
// registry, code uses the same Monaco editor in read-only mode.

import dynamic from 'next/dynamic';
import { AlertTriangle, ExternalLink } from '@/lib/icons';
import { Markdown } from '@/components/chat/markdown';
import { ResponseView } from '@/components/response/response-view';
import type { CanvasContent } from '@/lib/canvas/content';

const CodeViewer = dynamic(() => import('./code-editor'), { ssr: false });

export interface CanvasViewerProps {
  content: CanvasContent;
  onFollowup?: (prompt: string) => void;
}

export function CanvasViewer({ content, onFollowup }: CanvasViewerProps) {
  if (content.kind === 'markdown' && content.markdown != null) {
    return (
      <article className="mx-auto w-full max-w-[72ch] text-[15px] leading-relaxed">
        <Markdown content={content.markdown} onFollowup={onFollowup} />
      </article>
    );
  }

  if (content.kind === 'code' && content.code) {
    return (
      <div className="h-full min-h-[320px] w-full overflow-hidden rounded-xl border border-border/30">
        <CodeViewer
          content={content.code.text}
          language={content.code.language ?? null}
          editable={false}
          onChange={() => {}}
        />
      </div>
    );
  }

  if (content.kind === 'report' && content.response) {
    return (
      <div className="mx-auto w-full max-w-[860px]">
        <ResponseView response={content.response} onFollowup={onFollowup} showActions={false} showNotice />
      </div>
    );
  }

  if (content.kind === 'image' && content.url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={content.url} alt={content.title} className="mx-auto max-h-full max-w-full rounded-xl object-contain" />;
  }

  if (content.kind === 'url' && content.url) {
    return (
      <div className="flex h-full min-h-[320px] flex-col gap-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground/70">
          <AlertTriangle className="h-3.5 w-3.5" />
          Sandboxed preview — scripts are disabled.
          <a href={content.url} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-sky-400 hover:underline">
            Open external <ExternalLink className="h-3 w-3" />
          </a>
        </div>
        <iframe
          title={content.title}
          src={content.url}
          sandbox=""
          referrerPolicy="no-referrer"
          className="min-h-0 flex-1 rounded-xl border border-border/30 bg-white/5"
        />
      </div>
    );
  }

  return <p className="text-sm text-muted-foreground/70">Nothing to display.</p>;
}
