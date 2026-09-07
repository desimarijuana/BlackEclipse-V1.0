'use client';

import { useState, useEffect, useRef } from 'react';
import dynamic from 'next/dynamic';
import { Sidebar, AppTab, Conversation } from '@/components/layout/sidebar';
import { TopBar } from '@/components/layout/top-bar';
import { EmptyState } from '@/components/chat/empty-state';
import { ChatHistory } from '@/components/chat/chat-history';
import { ChatInput } from '@/components/chat/chat-input';
import { Message } from '@/types/chat';

// Screens — heavy ones (ECharts, WebGL bubbles, charts) are code-split and
// only fetched when their tab is opened, so the first paint compiles/loads
// just the chat shell instead of the whole app.
import type { NewsItem } from './market-news';

const MarketOverviewScreen = dynamic(
  () => import('./market-overview').then((m) => m.MarketOverviewScreen),
  { ssr: false, loading: () => <ScreenSkeleton /> }
);
const MarketBubbles = dynamic(() => import('./market-bubbles').then((m) => m.MarketBubbles), {
  ssr: false,
  loading: () => <ScreenSkeleton />,
});
const MarketNews = dynamic(() => import('./market-news').then((m) => m.MarketNews), {
  ssr: false,
  loading: () => <ScreenSkeleton />,
});
const EmbeddedChart = dynamic(() => import('./embedded-chart').then((m) => m.EmbeddedChart), {
  ssr: false,
  loading: () => <ScreenSkeleton />,
});
const Settings = dynamic(() => import('./settings').then((m) => m.Settings), { ssr: false });
const AlertsScreen = dynamic(() => import('@/app/alerts/alerts-client').then((m) => m.AlertsClient), {
  ssr: false,
  loading: () => <ScreenSkeleton />,
});
const EconomicsScreen = dynamic(() => import('./economics/economics').then((m) => m.EconomicsScreen), {
  ssr: false,
  loading: () => <ScreenSkeleton />,
});
const PortfolioScreen = dynamic(() => import('./portfolio').then((m) => m.PortfolioScreen), {
  ssr: false,
  loading: () => <ScreenSkeleton />,
});

import { Newspaper, ArrowLeft } from 'lucide-react';
import { TooltipProvider } from '@/components/ui/tooltip';
import Aurora from '@/components/ui/Aurora';
import { getAgentProvider } from '@/lib/agent/registry';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { TopLoader } from '@/components/ui/top-loader';
import { cn } from '@/lib/utils';

function ScreenSkeleton() {
  // Chunk-load placeholder for next/dynamic screens. Kept minimal and
  // non-competitive with TopLoader (the single real data loader).
  return <TopLoader />;
}

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
  // Tier-weighted 24h news sentiment score in [-1, 1] from the news feed.
  const [newsScore, setNewsScore] = useState(0);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Keep-alive tabs: a tab mounts on first visit and stays mounted (hidden
  // with display:none) after that. Boot mounts ONLY the initial tab, so we
  // keep the old boot behavior (one screen fetching, no mount-all race),
  // while revisits are instant — no chunk reload, no refetch, no loader.
  const [visited, setVisited] = useState<Set<AppTab>>(() => new Set(['chat']));
  useEffect(() => {
    setVisited(prev => (prev.has(activeTab) ? prev : new Set(prev).add(activeTab)));
  }, [activeTab]);

  // Deep-link boot: /?symbol=AAPL opens that symbol's chart tab directly.
  // Powers ctrl+click "open in new tab" from the screener tables.
  useEffect(() => {
    if (!mounted) return;
    try {
      const params = new URLSearchParams(window.location.search);
      const sym = params.get('symbol');
      if (sym) {
        setSelectedChartSymbol(sym.toUpperCase());
        setActiveTab('chart');
        // Clean the URL so refresh keeps the chart (history replace).
        window.history.replaceState(null, '', '/');
      }
    } catch { /* ignore malformed URLs */ }
  }, [mounted]);

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

  /** Inject a prompt and get a REAL answer from the research engine
   *  (/api/agent/research) — never a canned fabricated reply. */
  const runResearchPrompt = async (chatId: string, userText: string) => {
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
  };

  const handleInjectPrompt = (ticker: string, promptType: 'research' | 'discuss', customContext?: string) => {
    setActiveTab('chat');

    const customPrompt = promptType === 'research'
      ? `Generate a comprehensive AI research report on ${ticker} detailing financial health, P/E ratios, and growth vectors.`
      : `What is the market sentiment and outlook on ${ticker} given recent institutional activity?`;

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: customPrompt };
    const chatId = addMessageToActiveChat(userMsg);

    if (customContext) {
      // Caller-provided context (e.g. screener row data) is shown verbatim as
      // data context, then real research runs on top of it.
      const ctxMsg: Message = {
        id: (Date.now() + 3).toString(),
        role: 'assistant',
        content: `Data context for "${ticker}":\n\n${customContext}`,
      };
      appendAssistantReply(chatId, ctxMsg);
    }
    void runResearchPrompt(chatId, customContext ? `${customPrompt}\n\nContext data: ${customContext}` : customPrompt);

    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDiscussNews = (news: NewsItem) => {
    setActiveTab('chat');
    const prompt = `Discuss the market implications of: "${news.headline}" for ${news.ticker || 'the market'}.`;

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: prompt };
    const chatId = addMessageToActiveChat(userMsg);
    void runResearchPrompt(chatId, prompt);

    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleChartTicker = (symbol?: string) => {
    if (symbol) {
      setSelectedChartSymbol(symbol);
    }
    setActiveTab('chart');
  };

  // ── Blended site-wide sentiment (drives the aurora glow) ────────────────
  // Index sentiment (from the screener: equity averages + breadth) and news
  // sentiment (tier-weighted 24h pulse) each vote; news acts as a tiebreaker
  // / confirmer, not a standalone flipper. Hysteresis: |net| ≤ 0.12 keeps
  // the previous glow so quiet periods don't strobe.
  const lastAuroraBullishRef = useRef(true);
  const auroraBullish = (() => {
    const newsVote = newsScore > 0.15 ? 1 : newsScore < -0.15 ? -1 : 0;
    const net = (isMarketBullish ? 1 : -1) + newsVote * 0.5;
    if (net > 0.12) lastAuroraBullishRef.current = true;
    else if (net < -0.12) lastAuroraBullishRef.current = false;
    return lastAuroraBullishRef.current;
  })();

  return (
    <TooltipProvider delay={0}>
    <div className="relative flex flex-col md:flex-row h-[100dvh] w-full bg-background text-foreground font-sans selection:bg-primary/30 overflow-hidden">
      {/* Aurora full-viewport top glow — reacts to blended market + news sentiment */}
      <div
        className="absolute top-0 left-0 right-0 h-56 z-0 pointer-events-none overflow-hidden"
        style={{
          maskImage: 'linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,0.4) 70%, rgba(0,0,0,0) 100%)',
          WebkitMaskImage: 'linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,0.4) 70%, rgba(0,0,0,0) 100%)',
        }}
      >
        <Aurora
          colorStops={
            auroraBullish
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

      <div className="flex-1 flex flex-col relative z-10 overflow-hidden backdrop-blur-3xl bg-white/30 dark:bg-[#0f0f0f]/30 min-w-0 h-full before:pointer-events-none before:absolute before:inset-x-0 before:top-0 before:h-px before:bg-gradient-to-r before:from-transparent before:via-white/60 dark:before:via-white/10 before:to-transparent">
        <TopBar 
          onToggleMenu={() => setMobileMenuOpen(true)}
        />

        <div className="flex-1 overflow-y-auto relative w-full h-full z-10">
          {/* Keep-alive tabs: a tab mounts on first visit (visited set) and
              then stays mounted hidden — revisits are instant with no chunk
              reload, no refetch, no loader flash. Unvisited tabs render
              nothing, preserving the old single-screen boot behavior. */}
          {visited.has('chat') && (
            <div className={activeTab === 'chat' ? 'w-full h-full' : 'hidden'}>
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
            </div>
          )}

          {visited.has('news') && (
            <div className={cn('w-full h-full', activeTab === 'news' ? '' : 'hidden')}>
              <div className="flex-1 w-full max-w-7xl mx-auto px-4 md:px-8 py-8 overflow-y-auto h-full pb-20">
                <div className="animate-fade-in-up w-full h-full flex flex-col">
                  <div className="mb-6 flex items-center gap-2 border-b border-border/10 pb-3">
                    <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
                      <Newspaper className="text-primary" size={30} />
                    </div>
                    <div>
                      <h1 className="font-serif text-2xl font-semibold tracking-tight text-foreground">Market News & Bulletins</h1>
                      <p className="text-muted-foreground text-xs mt-0.5">Live updates, professional ratings indicators, and direct discuss-to-chat triggers.</p>
                    </div>
                  </div>
                  <MarketNews
                    onDiscussNews={handleDiscussNews}
                    onAnalyzeTicker={handleChartTicker}
                    fullPage={true}
                    onNewsSentiment={setNewsScore}
                  />
                </div>
              </div>
            </div>
          )}

          {visited.has('discovery') && (
            <div className={cn('w-full h-full', activeTab === 'discovery' ? '' : 'hidden')}>
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
            </div>
          )}

          {visited.has('heatmap') && (
            <div className={cn('w-full h-full', activeTab === 'heatmap' ? '' : 'hidden')}>
              <MarketBubbles onAnalyzeTicker={t => handleInjectPrompt(t, 'research')} />
            </div>
          )}

          {visited.has('alerts') && (
            <div className={cn('w-full h-full', activeTab === 'alerts' ? '' : 'hidden')}>
              <div className="flex-1 overflow-y-auto">
                <AlertsScreen />
              </div>
            </div>
          )}

          {visited.has('economics') && (
            <div className={cn('w-full h-full', activeTab === 'economics' ? '' : 'hidden')}>
              <EconomicsScreen />
            </div>
          )}

          {visited.has('portfolio') && (
            <div className={cn('w-full h-full', activeTab === 'portfolio' ? '' : 'hidden')}>
              <div className="flex-1 w-full max-w-7xl mx-auto px-4 md:px-8 py-8">
                <PortfolioScreen />
              </div>
            </div>
          )}

          {visited.has('chart') && (
            <div className={cn('w-full h-full', activeTab === 'chart' ? '' : 'hidden')}>
              <div className="flex-1 w-full max-w-7xl mx-auto px-4 md:px-8 py-6 h-full">
                <button
                  onClick={() => setActiveTab('discovery')}
                  className="mb-3 inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-primary border border-border/40 hover:border-primary/40 bg-accent/30 hover:bg-accent/60 rounded-xl px-3 py-1.5 transition-all cursor-pointer"
                >
                  <ArrowLeft size={13} /> Back to Market Screener
                </button>
                <EmbeddedChart symbol={selectedChartSymbol} />
              </div>
            </div>
          )}
        </div>
      </div>

      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="w-[calc(100%-2rem)] max-w-6xl sm:max-w-6xl h-[min(90dvh,880px)] p-0 gap-0 overflow-hidden rounded-2xl border border-white/10 bg-white/70 dark:bg-[#0f0f0f]/70 backdrop-blur-2xl shadow-2xl text-foreground">
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
