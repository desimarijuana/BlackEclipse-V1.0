import type { GalleryBlock } from '@/lib/response/contract';
import { ImageGallery } from '@/components/chat/image-gallery';

/**
 * The `gallery` response block → inline images. The block was validated by the
 * response contract (http(s)-only image URLs), so this is a thin presentational
 * wrapper: the actual grid + lightbox live in the shared `ImageGallery`.
 */
export function GalleryBlockView({ block, compact = false }: { block: GalleryBlock; compact?: boolean }) {
  if (!block.images?.length) return null;
  return (
    <figure className="w-full">
      {block.title ? (
        <figcaption className="mb-1.5 text-sm font-semibold text-foreground">{block.title}</figcaption>
      ) : null}
      <ImageGallery images={block.images} columns={block.columns} compact={compact} />
      {block.caption || block.source ? (
        <p className="mt-1 text-[10px] text-muted-foreground/60">
          {block.caption}
          {block.caption && block.source ? ' · ' : ''}
          {block.source}
        </p>
      ) : null}
    </figure>
  );
}
