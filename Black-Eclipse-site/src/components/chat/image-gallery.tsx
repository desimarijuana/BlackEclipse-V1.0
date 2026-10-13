'use client';

import { useCallback, useEffect, useId, useState } from 'react';
import { Image as ImageIcon, ExternalLink, X, AlertTriangle } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { coerceGalleryImages, coerceGalleryBlob, type GalleryItem } from '@/lib/image-gallery-view';

/**
 * The inline image gallery — the ONE renderer for internet images.
 *
 * Renders validated image results (from an `image_search` tool result or a
 * response `gallery` block) as a responsive grid with a larger-image lightbox.
 * Broken/inaccessible images degrade to a labeled fallback card, never a crash
 * or an empty box. No arbitrary model-generated HTML is executed: every value is
 * typed and the image URL was scheme-checked before it reached this component.
 */
export function ImageGallery({
  images,
  columns,
  compact = false,
  className,
}: {
  images: unknown;
  columns?: number;
  compact?: boolean;
  className?: string;
}) {
  const items = galleryItems(images);
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  if (items.length === 0) return null;
  const cols = columns && columns >= 1 && columns <= 4 ? columns : undefined;
  return (
    <div className={cn('w-full', className)}>
      <div
        className={cn(
          'grid gap-2',
          cols ? columnClass(cols) : 'grid-cols-2 sm:grid-cols-3',
        )}
      >
        {items.map((item, i) => (
          <GalleryCard key={item.id} item={item} compact={compact} onOpen={() => setOpenIndex(i)} />
        ))}
      </div>
      {openIndex !== null ? (
        <Lightbox
          items={items}
          index={openIndex}
          onClose={() => setOpenIndex(null)}
          onNavigate={setOpenIndex}
        />
      ) : null}
    </div>
  );
}

function galleryItems(images: unknown): GalleryItem[] {
  // Accept a bare array OR a run blob (`{ results: [...] }`).
  if (Array.isArray(images)) return coerceGalleryImages(images);
  return coerceGalleryBlob(images).items;
}

function columnClass(cols: number): string {
  if (cols === 1) return 'grid-cols-1';
  if (cols === 2) return 'grid-cols-2';
  if (cols === 3) return 'grid-cols-2 sm:grid-cols-3';
  return 'grid-cols-2 sm:grid-cols-4';
}

function GalleryCard({ item, compact, onOpen }: { item: GalleryItem; compact: boolean; onOpen: () => void }) {
  const [broken, setBroken] = useState(false);
  const src = item.thumbnailUrl ?? item.imageUrl;
  return (
    <figure
      className={cn(
        'group/card overflow-hidden rounded-xl border border-border/20 glass-card-subtle',
        compact ? 'text-[10px]' : 'text-[11px]',
      )}
    >
      <button
        type="button"
        onClick={onOpen}
        className="relative block w-full cursor-zoom-in focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
        aria-label={`View larger image: ${item.title}`}
      >
        {broken ? (
          <div className="flex aspect-[4/3] w-full flex-col items-center justify-center gap-1.5 bg-muted/20 px-2 text-center">
            <AlertTriangle size={16} className="text-amber-500/80" />
            <span className="line-clamp-2 break-words text-muted-foreground/80">Image unavailable</span>
          </div>
        ) : (
          // Plain <img>: the project has no next/image remote config, and this
          // keeps arbitrary remote hosts out of the Next optimizer allowlist.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt={item.alt}
            width={item.width ?? undefined}
            height={item.height ?? undefined}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onError={() => setBroken(true)}
            className="aspect-[4/3] w-full bg-muted/10 object-cover transition-transform duration-200 group-hover/card:scale-[1.02]"
          />
        )}
      </button>
      <figcaption className="space-y-0.5 px-2 py-1.5">
        <p className="line-clamp-2 break-words font-medium text-foreground/90" title={item.title}>
          {item.title}
        </p>
        {item.sourceUrl ? (
          <a
            href={item.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex max-w-full items-center gap-1 text-muted-foreground/70 transition-colors hover:text-foreground"
          >
            <ImageIcon size={10} className="shrink-0 text-primary/70" />
            <span className="truncate">{item.sourceDomain || 'source'}</span>
            <ExternalLink size={9} className="shrink-0 opacity-60" />
          </a>
        ) : (
          <span className="inline-flex items-center gap-1 text-muted-foreground/60">
            <ImageIcon size={10} className="shrink-0 text-primary/70" />
            <span className="truncate">{item.sourceDomain || 'source'}</span>
          </span>
        )}
      </figcaption>
    </figure>
  );
}

function Lightbox({
  items,
  index,
  onClose,
  onNavigate,
}: {
  items: GalleryItem[];
  index: number;
  onClose: () => void;
  onNavigate: (i: number) => void;
}) {
  const item = items[index];
  const titleId = useId();
  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowRight') onNavigate((index + 1) % items.length);
      else if (e.key === 'ArrowLeft') onNavigate((index - 1 + items.length) % items.length);
    },
    [index, items.length, onClose, onNavigate],
  );
  useEffect(() => {
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [handleKey]);

  if (!item) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={item.title}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4 supports-backdrop-filter:backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl glass-card-strong"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2 border-b border-border/20 px-3 py-2">
          <p id={titleId} className="line-clamp-1 min-w-0 break-words text-[13px] font-medium text-foreground/90">
            {item.title}
          </p>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded-full p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>
        <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-black/20 p-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={item.imageUrl}
            alt={item.alt}
            className="max-h-[70vh] w-auto max-w-full object-contain"
            referrerPolicy="no-referrer"
          />        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-[11px] text-muted-foreground/80">
          <span className="truncate">
            {[item.sourceDomain, item.width && item.height ? `${item.width}×${item.height}` : null, item.attribution]
              .filter(Boolean)
              .join(' · ')}
          </span>
          {item.sourceUrl ? (
            <a
              href={item.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-foreground/80 transition-colors hover:text-foreground"
            >
              Open source <ExternalLink size={11} />
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/**
 * The runtime-collected image panel — attached to an assistant turn that used
 * `image_search`/`render_image_gallery`. Mirrors `VisionPanel`: an always-visible
 * summary line that expands to the gallery. Renders nothing for an absent blob,
 * so existing turns are unaffected.
 */
export function ImageGalleryPanel({
  images,
  compact = false,
}: {
  images: unknown;
  compact?: boolean;
}) {
  const view = coerceGalleryBlob(images);
  const [open, setOpen] = useState(true);
  if (view.items.length === 0 && view.failures.length === 0) return null;
  const summary =
    view.items.length > 0
      ? `${view.items.length} image${view.items.length === 1 ? '' : 's'}`
      : 'No images available';
  return (
    <div className={cn('mt-3 w-full rounded-xl border border-border/20 glass-card-subtle', compact ? 'p-2' : 'p-2.5')}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="mb-1 flex w-full items-center gap-1.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
      >
        <ImageIcon size={11} className="shrink-0 text-primary" />
        <span className="font-medium text-foreground/90">Image search</span>
        <span className="text-muted-foreground/80">· {summary}</span>
      </button>
      {open && view.items.length > 0 ? <ImageGallery images={view.items} compact={compact} /> : null}
      {view.failures.length > 0 && view.items.length === 0 ? (
        <p className="px-1 text-[11px] text-amber-500/90">
          Image results were unavailable — no verified internet images to show.
        </p>
      ) : null}
    </div>
  );
}
