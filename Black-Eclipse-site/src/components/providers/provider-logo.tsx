// ── ProviderLogo ───────────────────────────────────────────────────────────
// The provider's actual brand mark, rendered as a `currentColor` mask so it
// reads correctly in both themes. A provider with no brand asset (custom,
// auto, mock, an unknown id) gets a neutral CPU glyph — never a sparkle.

import { Cpu } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { providerLogoAsset } from '@/lib/providers/logo';

export interface ProviderLogoProps {
  /** Provider id (`openai`, `ollama`, …) or a display label (`Ollama (local)`). */
  provider: string | null | undefined;
  size?: number;
  className?: string;
}

export function ProviderLogo({ provider, size = 14, className }: ProviderLogoProps) {
  const asset = providerLogoAsset(provider);
  if (!asset) {
    return (
      <Cpu
        size={size}
        aria-hidden
        className={cn('shrink-0 text-muted-foreground', className)}
      />
    );
  }
  return (
    <span
      aria-hidden
      className={cn('inline-block shrink-0 bg-current', className)}
      style={{
        width: size,
        height: size,
        maskImage: `url("${asset}")`,
        WebkitMaskImage: `url("${asset}")`,
        maskRepeat: 'no-repeat',
        WebkitMaskRepeat: 'no-repeat',
        maskPosition: 'center',
        WebkitMaskPosition: 'center',
        maskSize: 'contain',
        WebkitMaskSize: 'contain',
      }}
    />
  );
}

export default ProviderLogo;
