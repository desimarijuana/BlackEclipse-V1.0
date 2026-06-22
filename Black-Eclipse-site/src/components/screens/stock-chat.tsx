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
import { CryptoBubbles } from './crypto-bubbles';
import { MarketNews, NewsItem } from './market-news';

import { MyPortfolio } from './my-portfolio';
import { BacktestDashboard } from './backtest-dashboard';
import { Newspaper, SlidersHorizontal } from 'lucide-react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AuthProvider, useAuth } from '@/components/auth/auth-context';
import { AuthRequiredDialog } from '@/components/auth/auth-required-dialog';
import Aurora from '@/components/ui/Aurora';

function StockChatContent() {
  const { user, requireAuth } = useAuth();
  const [activeTab, setActiveTab] = useState<AppTab>('chat');
  const [query, setQuery] = useState('');
  const [selectedChartSymbol, setSelectedChartSymbol] = useState('AAPL');
  
  // Conversations states
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  
  const [isDark, setIsDark] = useState(true);
  const [mounted, setMounted] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isMarketBullish, setIsMarketBullish] = useState(true);
  const [isNewsBullish, setIsNewsBullish] = useState(true);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Sync theme
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  // Load conversations from local storage
  useEffect(() => {
    if (!mounted) return;
    const key = user ? `chats_${user.id}` : 'chats_guest';
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
  }, [user, mounted]);

  const saveConversations = (updated: Conversation[]) => {
    setConversations(updated);
    const key = user ? `chats_${user.id}` : 'chats_guest';
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

  // Helper to add messages
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
        // Move active conversation to the top
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

  const handleSend = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    requireAuth(() => {
      const userText = query;
      const userMsg: Message = { id: Date.now().toString(), role: 'user', content: userText };
      setQuery('');
      
      const chatId = addMessageToActiveChat(userMsg);
      
      setTimeout(() => {
        const replyMsg: Message = { 
          id: (Date.now() + 1).toString(), 
          role: 'assistant', 
          content: `Analyzing stock data for your request: "${userText}". Market conditions suggest strong momentum in the tech sector today. Here is our assessment: NVDA and AAPL are showing strong accumulation, while TSLA has consolidated support near $175.` 
        };
        appendAssistantReply(chatId, replyMsg);
      }, 1000);
    });
  };

  const handleInjectPrompt = (ticker: string, promptType: 'research' | 'discuss', customContext?: string) => {
    requireAuth(() => {
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
    });
  };

  const handleDiscussNews = (news: NewsItem) => {
    requireAuth(() => {
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
    });
  };

  const handleChartTicker = (symbol?: string) => {
    if (symbol) {
      setSelectedChartSymbol(symbol);
    }
    setActiveTab('backtest');
  };

  return (
    <TooltipProvider delay={0}>
    <div className="flex flex-col md:flex-row h-[100dvh] w-full bg-background text-foreground font-sans selection:bg-primary/30 overflow-hidden">
      <Sidebar 
        activeTab={activeTab} 
        onChangeTab={setActiveTab} 
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteConversation={handleDeleteConversation}
        mobileOpen={mobileMenuOpen}
        onCloseMobile={() => setMobileMenuOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col relative overflow-hidden backdrop-blur-3xl min-w-0 h-full">
        {/* Dynamic Viewport Market Screener, Portfolio & News Glow (Placed behind top-right of TopBar header when in Screener, Portfolio, or News tab) */}
        {(activeTab === 'discovery' || activeTab === 'market' || activeTab === 'news') && (
          <div 
            className="absolute top-0 left-0 w-full h-[240px] pointer-events-none z-0 overflow-hidden"
            style={{
              filter: 'blur(50px)',
              maskImage: 'linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,0.3) 70%, rgba(0,0,0,0) 100%)',
              WebkitMaskImage: 'linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,0.3) 70%, rgba(0,0,0,0) 100%)',
              opacity: isDark ? 0.7 : 0.5,
              transition: 'opacity 1s ease',
            }}
          >
            <Aurora
              colorStops={
                activeTab === 'news'
                  ? (isNewsBullish
                      ? (isDark ? ["#022c22", "#7aff78", "#022c22"] : ["#064e3b", "#047857", "#064e3b"])
                      : (isDark ? ["#450a0a", "#ff3e3e", "#450a0a"] : ["#7f1d1d", "#ef4444", "#7f1d1d"]))
                  : (isMarketBullish
                      ? (isDark ? ["#022c22", "#7aff78", "#022c22"] : ["#064e3b", "#047857", "#064e3b"])
                      : (isDark ? ["#450a0a", "#ff3e3e", "#450a0a"] : ["#7f1d1d", "#ef4444", "#7f1d1d"]))
              }
              blend={0.95}
              amplitude={1.5}
              speed={1.6}
            />
          </div>
        )}

        <TopBar 
          isDark={isDark} 
          onToggleTheme={() => setIsDark(!isDark)} 
          onToggleMenu={() => setMobileMenuOpen(true)}
        />

        {/* Tab Switcher rendering */}
        <div className="flex-1 overflow-y-auto relative w-full h-full">
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

                  {/* Bottom Input Area */}
                  <div className="w-full max-w-4xl relative group mt-auto shrink-0 pb-2 md:pb-4">
                    <div className="absolute -inset-1 bg-gradient-to-r from-primary/20 via-accent/20 to-primary/20 rounded-[2rem] blur-xl opacity-0 group-focus-within:opacity-100 transition duration-500 pointer-events-none"></div>
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
                    setActiveTab('backtest');
                  }}
                  embedded={false} 
                  onMarketStatusChange={setIsMarketBullish}
                />
              </div>
            </div>
          )}

          {activeTab === 'heatmap' && (
            <CryptoBubbles onAnalyzeTicker={t => handleInjectPrompt(t, 'research')} />
          )}

          {activeTab === 'backtest' && (
            <div className="flex-1 w-full max-w-7xl mx-auto px-4 md:px-8 py-8 overflow-y-auto h-full scrollbar-hide pb-20">
              <div className="animate-fade-in-up w-full h-full flex flex-col">
                <div className="mb-6 flex items-center gap-2 border-b border-border/10 pb-3">
                  <SlidersHorizontal className="text-primary w-7 h-7" />
                  <div>
                    <h1 className="font-serif text-2xl font-semibold tracking-tight text-foreground">Strategy Backtesting Engine</h1>
                    <p className="text-muted-foreground text-xs mt-0.5">Test quantitative trading strategies against years of historical pricing data.</p>
                  </div>
                </div>
                <BacktestDashboard />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Global Interceptor Dialog Modal */}
      <AuthRequiredDialog />
    </div>
    </TooltipProvider>
  );
}

export function StockChat() {
  return (
    <AuthProvider>
      <StockChatContent />
    </AuthProvider>
  );
}
