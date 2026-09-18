import { useEffect, useRef } from 'react';
import { Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Message } from '@/types/chat';

interface ChatHistoryProps {
  messages: Message[];
  /**
   * `false` (default) is the full-page ChatBot layout (centered 4xl column).
   * `true` fills a narrow container (e.g. the floating ChatDock) edge-to-edge.
   */
  compact?: boolean;
}

export function ChatHistory({ messages, compact = false }: ChatHistoryProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className={cn(
      'flex-1 w-full overflow-y-auto scrollbar-hide min-h-0',
      compact ? 'space-y-3 p-3' : 'max-w-4xl pr-2 space-y-6 pb-6',
    )}>
      <div className={compact ? 'space-y-3' : 'space-y-6'}>
        {messages.map((msg) => (
          <div 
            key={msg.id}
            className={`animate-fade-in-up flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            {msg.role === 'assistant' && !compact && (
              <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary mb-2 border border-primary/20">
                <Sparkles size={14} />
              </div>
            )}
            <div className={cn(
              'leading-relaxed break-words whitespace-pre-wrap',
              compact
                ? 'px-3 py-2 max-w-[90%] text-[13px] rounded-2xl'
                : 'px-4 py-3 md:px-5 md:py-3.5 max-w-[92%] sm:max-w-[85%] text-[14px] md:text-[15px] rounded-[1.5rem] md:rounded-[2rem]',
              msg.role === 'user'
                ? 'bg-card text-foreground border border-border'
                : 'text-foreground glass-card border border-white/10 dark:border-white/5 shadow-lg shadow-black/10'
            )}>
              {msg.content}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
