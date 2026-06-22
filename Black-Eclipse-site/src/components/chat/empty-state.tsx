'use client';

import { TrendingUp } from 'lucide-react';
import { ChatInput } from './chat-input';
import { Button } from '@/components/ui/button';

interface EmptyStateProps {
  query: string;
  setQuery: (val: string) => void;
  onSend: (e: React.FormEvent) => void;
  onViewMarketOverview?: () => void;
}

export function EmptyState({ query, setQuery, onSend, onViewMarketOverview }: EmptyStateProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center w-full max-w-4xl mx-auto px-4 md:px-6 z-10 relative">
      {/* Background Glow Effect ONLY on Home Screen */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[300px] md:w-[600px] h-[300px] md:h-[400px] bg-primary/10 rounded-full blur-[80px] md:blur-[120px] pointer-events-none" />
      
      <h1 
        className="animate-fade-in-up text-3xl sm:text-4xl md:text-5xl font-medium text-foreground mb-8 md:mb-10 tracking-tight text-center"
      >
        Any new ideas to explore?
      </h1>

      <div 
        className="animate-fade-in-up [animation-delay:100ms] w-full max-w-3xl relative group"
      >
        <div className="absolute -inset-1 bg-gradient-to-r from-primary/20 via-accent/20 to-primary/20 rounded-[2rem] blur-xl opacity-0 group-focus-within:opacity-100 transition duration-500 pointer-events-none"></div>
        <ChatInput 
          query={query} 
          setQuery={setQuery} 
          onSend={onSend} 
          showModelSelect={true} 
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
