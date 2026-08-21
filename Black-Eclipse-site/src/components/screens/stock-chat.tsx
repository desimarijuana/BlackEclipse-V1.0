'use client';

import { useState, useEffect } from 'react';
import { Sidebar, AppTab, Conversation } from '@/components/layout/sidebar';
import { TopBar } from '@/components/layout/top-bar';
import { EmptyState } from '@/components/chat/empty-state';
import { ChatHistory } from '@/components/chat/chat-history';
import { ChatInput } from '@/components/chat/chat-input';
import { Message } from '@/types/chat';

// Screens imports
import { MarketOverviewScreen } from './market-overview';
import { MarketBubbles } from './market-bubbles';
import { MarketNews, NewsItem } from './market-news';

import { MyPortfolio } from './my-portfolio';
import { EmbeddedChart } from './embedded-chart';
import { Settings } from './settings';
import { Newspaper } from 'lucide-react';
import { TooltipProvider } from '@/components/ui/tooltip';
import Aurora from '@/components/ui/Aurora';
import { getAgentProvider } from '@/lib/agent/registry';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';

function StockChatContent() {
  const [activeTab, setActiveTab] = useState<AppTab>('chat');
  const [query, setQuery] = useState('');
  const [selectedChartSymbol, setSelectedChartSymbol] = useState('AAPL');
  
  // Conversations states
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  
  const [mounted, setMounted] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isMarketBullish, setIsMarketBullish] = useState(true);
  const [isNewsBullish, setIsNewsBullish] = useState(true);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Load conversations from local storage
  useEffect(() => {
    if (!mounted) return;
    const key = 'chats_guest';
    const saved = localStorage.getItem(key);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setConversations(parsed);
        if (parsed.length > 0) {
          setActiveConversationId(parsed[0].id);
          setMessages(parsed[0].messages);
        } else {
          setActiveConversationId(null);
          setMessages([]);
        }
      } catch (err) {
        console.error('Error loading conversations:', err);
      }
    } else {
      setConversations([]);
      setActiveConversationId(null);
      setMessages([]);
    }
  }, [mounted]);

  const saveConversations = (updated: Conversation[]) => {
    setConversations(updated);
    const key = 'chats_guest';
    localStorage.setItem(key, JSON.stringify(updated));
  };

  const handleSelectConversation = (id: string) => {
    setActiveConversationId(id);
    const chat = conversations.find(c => c.id === id);
    if (chat) {
      setMessages(chat.messages);
    }
  };

  const handleNewChat = () => {
    setActiveConversationId(null);
    setMessages([]);
  };

  const handleDeleteConversation = (id: string) => {
    const updated = conversations.filter(c => c.id !== id);
    saveConversations(updated);
    if (activeConversationId === id) {
      if (updated.length > 0) {
        setActiveConversationId(updated[0].id);
        setMessages(updated[0].messages);
      } else {
        setActiveConversationId(null);
        setMessages([]);
      }
    }
  };

  const addMessageToActiveChat = (userMsg: Message) => {
    let currentId = activeConversationId;
    let updatedConvs = [...conversations];
    
    if (!currentId) {
      currentId = 'chat_' + Date.now();
      const firstLine = userMsg.content;
      const title = firstLine.slice(0, 24) + (firstLine.length > 24 ? '...' : '');
      const newChat: Conversation = {
        id: currentId,
        title,
        messages: [userMsg],
        timestamp: Date.now()
      };
      updatedConvs = [newChat, ...updatedConvs];
      setActiveConversationId(currentId);
      setMessages([userMsg]);
    } else {
      const idx = updatedConvs.findIndex(c => c.id === currentId);
      if (idx !== -1) {
        const chat = updatedConvs[idx];
        const newMsgList = [...chat.messages, userMsg];
        updatedConvs[idx] = {
          ...chat,
          messages: newMsgList,
          timestamp: Date.now()
        };
        const [activeChat] = updatedConvs.splice(idx, 1);
        updatedConvs = [activeChat, ...updatedConvs];
        setMessages(newMsgList);
      }
    }
    
    saveConversations(updatedConvs);
    return currentId;
  };

  const appendAssistantReply = (chatId: string, replyMsg: Message) => {
    const updatedConvs = [...conversations];
    const idx = updatedConvs.findIndex(c => c.id === chatId);
    if (idx !== -1) {
      const chat = updatedConvs[idx];
      const newMsgList = [...chat.messages, replyMsg];
      updatedConvs[idx] = {
        ...chat,
        messages: newMsgList,
        timestamp: Date.now()
      };
      saveConversations(updatedConvs);
      if (activeConversationId === chatId) {
        setMessages(newMsgList);
      }
    }
  };

  const isResearchQuery = (text: string) =>
    /research|analy|report|invest|tell me about|fundamental|technical|sentiment|outlook|should i|worth|evaluate|deep dive|psx|kse/i.test(text);

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    const userText = query;
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: userText };
    setQuery('');
    
    const chatId = addMessageToActiveChat(userMsg);

    // Research intents go through the multi-agent research engine.
    if (isResearchQuery(userText)) {
      const thinkingMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Running multi-agent research... dispatching news, fundamentals, technical, and risk agents.',
      };
      appendAssistantReply(chatId, thinkingMsg);

      try {
        const res = await fetch('/api/agent/research', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: userText }),
        });
        const data = await res.json();
        const replyMsg: Message = {
          id: (Date.now() + 2).toString(),
          role: 'assistant',
          content: data.success
            ? data.answer
            : `Research failed: ${data.error || 'unknown error'}`,
        };
        appendAssistantReply(chatId, replyMsg);
      } catch (err) {
        const replyMsg: Message = {
          id: (Date.now() + 2).toString(),
          role: 'assistant',
          content: `Research error: ${err instanceof Error ? err.message : String(err)}`,
        };
        appendAssistantReply(chatId, replyMsg);
      }
      return;
    }

    // Otherwise ask the configured agent provider (falls back to the built-in mock).
    const provider = getAgentProvider();
    const history: { role: 'user' | 'assistant'; content: string }[] = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));
    const reply = await provider.chat([...history, { role: 'user', content: userText }]);

    const replyMsg: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: reply,
    };
    appendAssistantReply(chatId, replyMsg);
  };

  const handleInjectPrompt = (ticker: string, promptType: 'research' | 'discuss', customContext?: string) => {
    setActiveTab('chat');
    
    const customPrompt = promptType === 'research'
      ? `Generate a comprehensive AI research report on ${ticker} detailing financial health, P/E ratios, and growth vectors.`
      : `What is the market sentiment and outlook on ${ticker} given recent institutional activity?`;
      
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: customPrompt };
    const chatId = addMessageToActiveChat(userMsg);

    setTimeout(() => {
      const replyMsg: Message = { 
        id: (Date.now() + 1).toString(), 
        role: 'assistant', 
        content: customContext 
          ? `Performing autonomous AI intelligence scan on "${ticker}"...\n\n${customContext}`
          : `Performing autonomous AI intelligence scan on "${ticker}"... Analyzing P/E ratios, services revenue growth, and news sentiments. Technical indicators suggest immediate support thresholds are holding firmly, showing positive consolidation.`
      };
      appendAssistantReply(chatId, replyMsg);
    }, 1000);
    
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDiscussNews = (news: NewsItem) => {
    setActiveTab('chat');
    const prompt = `Discuss the market implications of: "${news.headline}" for ${news.ticker || 'the market'}.`;
    
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: prompt };
    const chatId = addMessageToActiveChat(userMsg);

    setTimeout(() => {
      const replyMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Analyzing the Bloomberg/Reuters bulletin on ${news.ticker || 'assets'}. The sentiment is classified as "${news.sentiment.toUpperCase()}" with an estimated impact of ${news.impactPercent}%. This shifts our technical weights toward short-term momentum flags in related industry groups.`
      };
      appendAssistantReply(chatId, replyMsg);
    }, 1000);
    
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleChartTicker = (symbol?: string) => {
    if (symbol) {
      setSelectedChartSymbol(symbol);
    }
    setActiveTab('chart');
  };

  return (
    <TooltipProvider delay={0}>
    <div className="relative flex flex-col md:flex-row h-[100dvh] w-full bg-background text-foreground font-sans selection:bg-primary/30 overflow-hidden">
      {/* Aurora full-viewport top glow — reacts to market sentiment */}
      <div
        className="absolute top-0 left-0 right-0 h-56 z-0 pointer-events-none overflow-hidden"
        style={{
          maskImage: 'linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,0.4) 70%, rgba(0,0,0,0) 100%)',
          WebkitMaskImage: 'linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,0.4) 70%, rgba(0,0,0,0) 100%)',
        }}
      >
        <Aurora
          colorStops={
            isMarketBullish
              ? ["#022c22", "#7aff78", "#022c22"]
              : ["#450a0a", "#ff3e3e", "#450a0a"]
          }
          blend={0.95}
          amplitude={1.5}
          speed={1.6}
        />
      </div>

      <Sidebar 
        activeTab={activeTab} 
        onChangeTab={setActiveTab} 
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteConversation={handleDeleteConversation}
        onOpenSettings={() => setSettingsOpen(true)}
        mobileOpen={mobileMenuOpen}
        onCloseMobile={() => setMobileMenuOpen(false)}
      />

      <div className="flex-1 flex flex-col relative z-10 overflow-hidden backdrop-blur-3xl min-w-0 h-full">
        <TopBar 
          onToggleMenu={() => setMobileMenuOpen(true)}
        />

        <div className="flex-1 overflow-y-auto relative w-full h-full z-10">
          {activeTab === 'chat' && (
            <div className="w-full h-full flex flex-col items-center justify-between p-4 md:p-6 relative min-w-0">
              {messages.length === 0 ? (
                <EmptyState 
                  query={query} 
                  setQuery={setQuery} 
                  onSend={handleSend} 
                  onViewMarketOverview={() => setActiveTab('discovery')}
                />
              ) : (
                <div className="flex-1 flex flex-col items-center w-full min-h-0 relative z-10 overflow-hidden justify-between">
                  <ChatHistory messages={messages} />
                  <div className="w-full max-w-4xl relative group mt-auto shrink-0 pb-2 md:pb-4">
                    <ChatInput 
                      query={query} 
                      setQuery={setQuery} 
                      onSend={handleSend} 
                      placeholder="Ask a follow-up..." 
                      showModelSelect={false} 
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'market' && (
            <MyPortfolio 
              onAnalyzeTicker={t => handleInjectPrompt(t, 'research')} 
              onMarketStatusChange={setIsMarketBullish}
            />
          )}

          {activeTab === 'news' && (
            <div className="flex-1 w-full max-w-5xl mx-auto px-4 md:px-8 py-8 overflow-y-auto h-full scrollbar-hide pb-20">
              <div className="animate-fade-in-up w-full h-full flex flex-col">
                <div className="mb-6 flex items-center gap-2 border-b border-border/10 pb-3">
                  <Newspaper className="text-primary w-7 h-7" />
                  <div>
                    <h1 className="font-serif text-2xl font-semibold tracking-tight text-foreground">Market News & Bulletins</h1>
                    <p className="text-muted-foreground text-xs mt-0.5">Live updates, professional ratings indicators, and direct discuss-to-chat triggers.</p>
                  </div>
                </div>
                <MarketNews 
                  onDiscussNews={handleDiscussNews} 
                  onAnalyzeTicker={handleChartTicker}
                  fullPage={true}
                  onNewsStatusChange={setIsNewsBullish}
                />
              </div>
            </div>
          )}

          {activeTab === 'discovery' && (
            <div className="flex-1 w-full max-w-7xl mx-auto px-4 md:px-8 py-8">
              <div className="animate-fade-in-up w-full h-full">
                <MarketOverviewScreen 
                  onAnalyzeTicker={(t: string, customCtx?: string) => handleInjectPrompt(t, 'research', customCtx)} 
                  onSelectChartSymbol={(sym) => {
                    setSelectedChartSymbol(sym);
                    setActiveTab('chart');
                  }}
                  embedded={false} 
                  onMarketStatusChange={setIsMarketBullish}
                />
              </div>
            </div>
          )}

          {activeTab === 'heatmap' && (
            <MarketBubbles onAnalyzeTicker={t => handleInjectPrompt(t, 'research')} />
          )}

          {activeTab === 'chart' && (
            <div className="flex-1 w-full max-w-7xl mx-auto px-4 md:px-8 py-6 h-full">
              <EmbeddedChart symbol={selectedChartSymbol} />
            </div>
          )}
        </div>
      </div>

      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="w-[calc(100%-2rem)] max-w-6xl sm:max-w-6xl h-[min(90dvh,880px)] p-0 gap-0 overflow-hidden rounded-none">
          <DialogTitle className="sr-only">Settings</DialogTitle>
          <Settings />
        </DialogContent>
      </Dialog>
    </div>
    </TooltipProvider>
  );
}

export function StockChat() {
  return <StockChatContent />;
}
