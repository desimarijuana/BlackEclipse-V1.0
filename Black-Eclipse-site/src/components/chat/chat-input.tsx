'use client';

import { useState } from 'react';
import { Plus, Mic, ChevronDown, ArrowUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

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

  return (
    <form onSubmit={onSend} className="relative flex items-center w-full bg-card rounded-[2rem] px-2 sm:px-4 py-1.5 border border-border shadow-lg shadow-black/20 focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/20 transition-all">
      <Button 
        type="button" 
        variant="ghost" 
        size="icon" 
        className="hidden sm:flex text-muted-foreground hover:text-foreground rounded-full hover:bg-accent shrink-0 h-10 w-10"
      >
        <Plus size={20} />
      </Button>
      
      <input 
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        className="flex-1 bg-transparent border-0 outline-none placeholder:text-muted-foreground text-foreground px-3 sm:px-4 text-base sm:text-lg min-w-0 w-full h-11 md:h-12 focus:outline-none focus:ring-0"
      />
      
      <div className="flex items-center gap-1 sm:gap-2 shrink-0">
        {showModelSelect && (
          <DropdownMenu>
            <DropdownMenuTrigger
              type="button"
              className="hidden min-[400px]:flex items-center gap-1.5 px-3 py-1.5 h-8 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground transition-colors text-xs sm:text-sm font-medium whitespace-nowrap cursor-pointer outline-none"
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
          className="p-2 text-muted-foreground hover:text-foreground rounded-full hover:bg-accent shrink-0 h-9 w-9"
        >
          <Mic size={18} className="sm:size-5" />
        </Button>
        <Button 
          type="submit" 
          size="icon" 
          disabled={!query.trim()}
          className="p-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-full shrink-0 h-9 w-9 cursor-pointer disabled:opacity-40 disabled:hover:bg-primary transition-opacity flex items-center justify-center"
        >
          <ArrowUp size={18} className="sm:size-5" />
        </Button>
      </div>
    </form>
  );
}
