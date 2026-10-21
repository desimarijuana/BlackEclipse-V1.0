'use client';

// Reading an attached paste. A pasted document is text the user handed over, so
// it must be readable back before it is sent — a chip you cannot open is a
// black box. Rendered as a glass dialog over the chat.

import { X } from '@/lib/icons';

export function AttachmentPreview({
  preview,
  onClose,
}: {
  preview: { name: string; text: string } | null;
  onClose: () => void;
}) {
  if (!preview) return null;
  return (
    <div
      className="fixed inset-0 z-[130] flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={preview.name}
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl glass-card-strong"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">{preview.name}</p>
            <p className="text-[11px] text-muted-foreground">
              {preview.text.length.toLocaleString()} characters · attached as context
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close preview"
            className="shrink-0 rounded-full p-1.5 text-muted-foreground hover:bg-white/10 hover:text-foreground"
          >
            <X size={15} />
          </button>
        </div>
        <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words px-4 py-3 text-[12.5px] leading-relaxed text-foreground/90">
          {preview.text}
        </pre>
      </div>
    </div>
  );
}
