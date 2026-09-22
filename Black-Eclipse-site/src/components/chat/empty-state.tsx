'use client';

import { BarChart3, Briefcase, LineChart, Newspaper, TrendingUp, Wand2 } from 'lucide-react';
import { ChatInput } from './chat-input';

interface EmptyStateProps {
  query: string;
  setQuery: (val: string) => void;
  onSend: (e: React.FormEvent) => void;
  onViewMarketOverview?: () => void;
  /** Opens the document picker — the composer "+" attaches context. */
  onAttach?: () => void;
  /** The assistant is working (rare here, but keeps the composer consistent). */
  busy?: boolean;
  onCancel?: () => void;
}

/**
 * Financial-native starting points. These are *examples*, not a capability
 * list — the composer still accepts anything, and the agent picks its own
 * tools. Each prompt exercises a different part of the harness (market data,
 * fundamentals, research, macro) so the first click demonstrates real range.
 */
const SUGGESTIONS: { icon: typeof LineChart; label: string; prompt: string }[] = [
  {
    icon: LineChart,
    label: 'Analyse a stock',
    prompt: 'Analyse NVDA: recent price action, valuation, and what is driving the move.',
  },
  {
    icon: BarChart3,
    label: 'Compare fundamentals',
    prompt: 'Compare the fundamentals of AAPL and MSFT — growth, margins, and valuation.',
  },
  {
    icon: Newspaper,
    label: 'Market sentiment',
    prompt: 'What is the current market sentiment and the main risks to watch this week?',
  },
  {
    icon: Briefcase,
    label: 'Portfolio review',
    prompt: 'Review the risk and diversification of a portfolio of AAPL, MSFT, and NVDA.',
  },
];

export function EmptyState({ query, setQuery, onSend, onViewMarketOverview, onAttach, busy, onCancel }: EmptyStateProps) {
  const pick = (prompt: string) => {
    setQuery(prompt);
    // Let the composer autosize before focusing the end of the text.
    requestAnimationFrame(() => {
      const form = document.querySelector<HTMLTextAreaElement>('[data-chat-composer] textarea');
      form?.focus();
      form?.setSelectionRange(prompt.length, prompt.length);
    });
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-center w-full max-w-4xl mx-auto px-4 md:px-6 z-10 relative">
      <div className="animate-fade-in-up mb-8 md:mb-10 flex flex-col items-center text-center">
        <span className="mb-4 flex h-11 w-11 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 text-primary">
          <Wand2 size={20} />
        </span>
        <h1 className="text-2xl sm:text-3xl md:text-4xl font-medium text-foreground tracking-tight">
          What should Eclipse investigate?
        </h1>
        <p className="mt-3 max-w-xl text-sm md:text-[15px] leading-relaxed text-muted-foreground">
          Ask about a stock, a portfolio, the macro backdrop, or a market move. Eclipse
          grounds every answer in live JDdS data and cites what it used.
        </p>
      </div>

      <div
        className="animate-fade-in-up [animation-delay:100ms] w-full max-w-3xl relative group"
        data-chat-composer
      >
        <ChatInput
          query={query}
          setQuery={setQuery}
          onSend={onSend}
          onAttach={onAttach}
          busy={busy}
          onCancel={onCancel}
        />
      </div>

      <div className="animate-fade-in [animation-delay:200ms] mt-6 md:mt-8 grid w-full max-w-3xl grid-cols-1 gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map(({ icon: Icon, label, prompt }) => (
          <button
            key={label}
            type="button"
            onClick={() => pick(prompt)}
            className="glass-card-subtle group/s flex items-start gap-3 rounded-2xl border border-white/10 dark:border-white/5 px-4 py-3 text-left transition-colors hover:border-primary/30 cursor-pointer"
          >
            <Icon size={16} className="mt-0.5 shrink-0 text-primary/80" />
            <span className="min-w-0">
              <span className="block text-[13px] font-medium text-foreground">{label}</span>
              <span className="mt-0.5 block truncate text-[12px] text-muted-foreground">{prompt}</span>
            </span>
          </button>
        ))}
      </div>

      <div className="animate-fade-in [animation-delay:300ms] w-full flex justify-center mt-6 md:mt-8">
        <button
          type="button"
          onClick={onViewMarketOverview}
          className="flex items-center gap-1.5 md:gap-2 px-5 md:px-6 py-2 md:py-2.5 rounded-full bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 transition-all shadow-lg shadow-primary/10 hover:shadow-xl hover:shadow-primary/20 text-xs md:text-sm font-medium h-auto cursor-pointer"
        >
          <TrendingUp size={14} className="md:size-[16px]" />
          View Market Overview
        </button>
      </div>
    </div>
  );
}
