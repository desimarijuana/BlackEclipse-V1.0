'use client';

// News detail/briefing dialog. Extracted from `market-news.tsx` (line budget)
// and shared by the live feed and the saved-news view.

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Bookmark, Sparkles } from '@/lib/icons';
import { relativeTime } from '@/lib/news/relative-time';
import type { NewsItem } from '@/components/screens/market-news';

export function NewsDetailDialog({
  item,
  saved,
  onClose,
  onToggleSaved,
  onDiscuss,
}: {
  item: NewsItem;
  saved: boolean;
  onClose: () => void;
  onToggleSaved: () => void;
  onDiscuss: () => void;
}) {
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="sm:max-w-2xl glass-card-strong border border-border/40 text-foreground rounded-2xl shadow-2xl p-6 overflow-hidden">
        {/* Ambient Background Blur Glow */}
        <div
          className={`absolute top-0 right-0 -translate-y-1/2 translate-x-1/2 w-72 h-72 rounded-full blur-[70px] pointer-events-none ${
            item.sentiment === 'bullish'
              ? 'bg-emerald-500/10'
              : item.sentiment === 'bearish'
              ? 'bg-rose-500/10'
              : 'bg-primary/10'
          }`}
        />

        <DialogHeader className="text-left relative z-10 pt-2">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold text-muted-foreground font-mono bg-accent px-2 py-1 rounded">
              {item.source}
            </span>
            {item.category && (
              <span className="text-[10px] font-bold text-primary/80 font-mono uppercase bg-primary/5 border border-primary/15 px-2 py-1 rounded">
                {item.category}
              </span>
            )}
            {item.ticker && (
              <span className="text-[10px] font-extrabold text-primary font-mono bg-primary/10 border border-primary/20 px-2 py-1 rounded">
                {item.ticker}
              </span>
            )}
            <span className="text-[10px] text-muted-foreground font-mono ml-auto">{relativeTime(item.timestamp)}</span>
          </div>
          <DialogTitle className="text-lg font-serif font-semibold leading-snug">
            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-primary hover:underline decoration-primary transition-all cursor-pointer"
              >
                {item.headline}
              </a>
            ) : (
              item.headline
            )}
          </DialogTitle>
          <div className="flex items-center gap-3 mt-3 border-b border-border/20 pb-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              Sentiment:
              <span
                className={`font-semibold capitalize px-2.5 py-0.5 rounded-full text-[10px] ${
                  item.sentiment === 'bullish'
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                    : item.sentiment === 'bearish'
                    ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                    : 'bg-neutral-500/10 text-neutral-400 border border-neutral-500/20'
                }`}
              >
                {item.sentiment}
              </span>
              {item.tier && (
                <span className="text-[10px] text-muted-foreground font-mono">Tier {item.tier}</span>
              )}
            </div>
            {item.url && (
              <div className="text-xs text-muted-foreground ml-auto">
                <a href={item.url} target="_blank" rel="noopener noreferrer" className="hover:text-primary transition-colors">
                  Open source article ↗
                </a>
              </div>
            )}
          </div>
        </DialogHeader>

        <div className="relative z-10 py-4 space-y-3.5 text-left text-xs leading-relaxed text-muted-foreground">
          <div>
            <span className="text-[10px] uppercase font-bold text-foreground tracking-wider block mb-1">Briefing Overview</span>
            <p>{item.summary || 'Open the source article for the full story.'}</p>
          </div>
          {(item.sourceCount ?? 1) > 1 && (
            <div className="p-2.5 bg-amber-400/5 border border-amber-400/20 rounded-xl">
              <span className="text-[10px] uppercase font-bold text-amber-400 tracking-wider block mb-1">Story Coverage</span>
              <p className="text-[11px] text-foreground">{(item.clusterSources || []).join(' · ')}</p>
            </div>
          )}
          {item.importanceReasons && item.importanceReasons.length > 0 && (
            <div className="p-2.5 bg-primary/5 border border-primary/20 rounded-xl">
              <span className="text-[10px] uppercase font-bold text-primary tracking-wider block mb-1">
                Why this is flagged · signal, not advice
              </span>
              <p className="text-[11px] text-foreground">{item.importanceReasons.join(' · ')}</p>
              <p className="text-[10px] text-muted-foreground mt-1 font-mono">
                {item.direction || item.sentiment} bias · {item.confidence || 'low'} confidence · {item.horizon || 'days'} horizon
              </p>
              {item.invalidates && item.invalidates[0] && (
                <p className="text-[10px] text-muted-foreground mt-1">
                  What would change this: {item.invalidates[0]}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex gap-2 mt-4 relative z-10 border-t border-border/20 pt-4 flex-wrap">
          <Button
            variant="outline"
            onClick={onClose}
            className="flex-1 min-w-[80px] rounded-xl text-xs py-2.5 h-auto border border-border/40 cursor-pointer"
          >
            Close
          </Button>
          <Button
            onClick={onToggleSaved}
            className={`flex-1 min-w-[60px] rounded-xl border text-xs py-2.5 h-auto cursor-pointer ${
              saved
                ? 'bg-amber-400/10 text-amber-400 border-amber-400/40'
                : 'bg-accent hover:bg-accent/80 text-accent-foreground border-border/40'
            }`}
          >
            <Bookmark size={13} className="mr-1.5" weight={saved ? 'fill' : 'regular'} />
            {saved ? 'Saved' : 'Save'}
          </Button>
          <Button
            onClick={onDiscuss}
            className="flex-1 min-w-[120px] inline-flex items-center justify-center gap-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 text-xs py-2.5 h-auto rounded-xl font-semibold cursor-pointer transition-all hover:scale-105"
          >
            <Sparkles size={13} /> Discuss
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
