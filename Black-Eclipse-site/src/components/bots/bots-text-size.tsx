'use client';

// Text-size control for the Bots workspace. Lives in the Bots sidebar header and
// the conversation header so the preference is reachable from both surfaces.
// The value is a local multiplier (`--bots-font-scale`), not a theme edit.

import { Check, Type } from '@/lib/icons';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  BOTS_FONT_SCALE_OPTIONS,
  useBotsAppearanceStore,
  useHydrateBotsAppearance,
} from '@/lib/bots/appearance';
import { cn } from '@/lib/utils';

export function BotsTextSizeMenu({ className }: { className?: string }) {
  useHydrateBotsAppearance();
  const fontScale = useBotsAppearanceStore((s) => s.appearance.fontScale);
  const setFontScale = useBotsAppearanceStore((s) => s.setFontScale);
  const reset = useBotsAppearanceStore((s) => s.reset);
  const current = Math.round(fontScale * 100);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            className={cn(
              'rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground',
              className,
            )}
            title="Bot text size"
            aria-label="Bot text size"
          />
        }
      >
        <Type size={13} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuLabel className="flex items-center justify-between gap-2">
          <span>Bot text size</span>
          <span className="text-[10px] font-normal text-muted-foreground">{current}%</span>
        </DropdownMenuLabel>
        {BOTS_FONT_SCALE_OPTIONS.map((option) => {
          const active = Math.abs(option.value - fontScale) < 0.001;
          return (
            <DropdownMenuItem key={option.label} onClick={() => setFontScale(option.value)}>
              <span className="flex-1">{option.label}</span>
              <span className="text-[10px] text-muted-foreground">
                {Math.round(option.value * 100)}%
              </span>
              <Check size={13} className={active ? 'text-primary' : 'opacity-0'} />
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={reset}>Reset to default</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
