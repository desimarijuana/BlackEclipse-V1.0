import { useEffect, useRef } from 'react';
import { Sparkles } from 'lucide-react';
import { Message } from '@/types/chat';

interface ChatHistoryProps {
  messages: Message[];
}

export function ChatHistory({ messages }: ChatHistoryProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex-1 w-full max-w-4xl overflow-y-auto pr-2 scrollbar-hide min-h-0 space-y-6 pb-6">
      <div className="space-y-6">
        {messages.map((msg) => (
          <div 
            key={msg.id}
            className={`animate-fade-in-up flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            {msg.role === 'assistant' && (
              <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary mb-2 border border-primary/20">
                <Sparkles size={14} />
              </div>
            )}
            <div className={`px-4 py-3 md:px-5 md:py-3.5 max-w-[92%] sm:max-w-[85%] text-[14px] md:text-[15px] leading-relaxed break-words ${
              msg.role === 'user' 
                ? 'bg-card text-foreground rounded-[1.5rem] md:rounded-[2rem] border border-border' 
                : 'text-foreground'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
