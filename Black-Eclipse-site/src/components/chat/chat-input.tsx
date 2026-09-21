'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Plus, Mic, ChevronDown, ArrowUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

// Grow the composer to roughly six lines, then scroll instead of growing.
const MAX_HEIGHT = 176;

interface ChatInputProps {
  query: string;
  setQuery: (val: string) => void;
  onSend: (e: React.FormEvent) => void;
  placeholder?: string;
  autoFocus?: boolean;
  showModelSelect?: boolean;
}

export function ChatInput({ 
  query, 
  setQuery, 
  onSend, 
  placeholder = "Ask about a stock, sector, or market trend...", 
  autoFocus,
  showModelSelect = true 
  }: ChatInputProps) {
  const [selectedModel, setSelectedModel] = useState('Flash-Lite');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow the composer with its content up to a cap, then scroll. A long
  // prompt no longer stays clipped on one line.
  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, []);

  useEffect(() => { resize(); }, [query, resize]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter inserts a newline. Ignore IME composition.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      onSend(e);
    }
  };

  return (
    <form onSubmit={onSend} className="relative flex items-end w-full glass-card border border-white/10 dark:border-white/5 rounded-3xl px-2 sm:px-4 py-1.5 shadow-lg shadow-black/20 focus-within:border-primary focus-within:glass-card transition-colors overflow-hidden">
      <Button 
        type="button" 
        variant="ghost" 
        size="icon" 
        className="hidden sm:flex text-muted-foreground hover:text-foreground rounded-full hover:bg-accent shrink-0 h-10 w-10 mb-1 focus-visible:ring-0 focus-visible:outline-none"
      >
        <Plus size={20} />
      </Button>
      
      <textarea 
        ref={textareaRef}
        rows={1}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        autoFocus={autoFocus}
        className="flex-1 self-center bg-transparent border-0 outline-none resize-none overflow-y-auto placeholder:text-muted-foreground text-foreground px-3 sm:px-4 py-3 text-base sm:text-lg leading-relaxed min-w-0 w-full focus:outline-none focus:ring-0"
      />
      
      <div className="flex items-center gap-1 sm:gap-2 shrink-0 mb-1">
        {showModelSelect && (
          <DropdownMenu>
            <DropdownMenuTrigger
              type="button"
              className="hidden min-[400px]:flex items-center gap-1.5 px-3 py-1.5 h-8 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground transition-colors text-xs sm:text-sm font-medium whitespace-nowrap cursor-pointer outline-none focus-visible:ring-0 focus-visible:outline-none"
            >
              {selectedModel} <ChevronDown size={14} />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-[140px]">
              <DropdownMenuItem onClick={() => setSelectedModel('Flash-Lite')}>
                Flash-Lite
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setSelectedModel('Flash')}>
                Flash
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setSelectedModel('Pro')}>
                Pro
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        <Button 
          type="button" 
          variant="ghost" 
          size="icon" 
          className="p-2 text-muted-foreground hover:text-foreground rounded-full hover:bg-accent shrink-0 h-9 w-9 focus-visible:ring-0 focus-visible:outline-none"
        >
          <Mic size={18} className="sm:size-5" />
        </Button>
        <Button 
          type="submit" 
          size="icon" 
          disabled={!query.trim()}
          className="p-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-full shrink-0 h-9 w-9 cursor-pointer disabled:opacity-40 disabled:hover:bg-primary transition-opacity flex items-center justify-center focus-visible:ring-0 focus-visible:outline-none"
        >
          <ArrowUp size={18} className="sm:size-5" />
        </Button>
      </div>
    </form>
  );
}
