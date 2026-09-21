'use client';

import { TrendingUp } from 'lucide-react';
import { ChatInput } from './chat-input';
import { Button } from '@/components/ui/button';

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

export function EmptyState({ query, setQuery, onSend, onViewMarketOverview, onAttach, busy, onCancel }: EmptyStateProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center w-full max-w-4xl mx-auto px-4 md:px-6 z-10 relative">
      <h1 
        className="animate-fade-in-up text-3xl sm:text-4xl md:text-5xl font-medium text-foreground mb-8 md:mb-10 tracking-tight text-center"
      >
        Any new ideas to explore?
      </h1>

      <div 
        className="animate-fade-in-up [animation-delay:100ms] w-full max-w-3xl relative group"
      >
        <ChatInput 
          query={query} 
          setQuery={setQuery} 
          onSend={onSend} 
          showModelSelect={true}
          onAttach={onAttach}
          busy={busy}
          onCancel={onCancel}
        />
      </div>

      <div 
        className="animate-fade-in [animation-delay:300ms] w-full flex justify-center mt-8 md:mt-12"
      >
         <Button 
           variant="outline"
           onClick={onViewMarketOverview}
           className="flex items-center gap-1.5 md:gap-2 px-5 md:px-6 py-2 md:py-2.5 rounded-full bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 transition-all shadow-lg shadow-primary/10 hover:shadow-xl hover:shadow-primary/20 text-xs md:text-sm font-medium h-auto cursor-pointer"
         >
           <TrendingUp size={14} className="md:size-[16px]" />
           View Market Overview
         </Button>
      </div>
    </div>
  );
}
