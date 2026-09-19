'use client';

import { useState, useEffect, useRef } from 'react';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import dynamic from 'next/dynamic';
import { Sidebar, AppTab, Conversation } from '@/components/layout/sidebar';
import { backTarget, recordVisit } from './navigation-history';
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
const ChartWidget = dynamic(() => import('@/components/chart/chart-widget').then((m) => m.ChartWidget), {
  ssr: false,
  loading: () => <ScreenSkeleton />,
});
const Settings = dynamic(() => import('./settings').then((m) => m.Settings), { ssr: false });
import type { SectionId } from './settings';
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
const JournalScreen = dynamic(() => import('@/components/journal/journal-screen').then((m) => m.JournalScreen), {
  ssr: false,
  loading: () => <ScreenSkeleton />,
});
const DashboardScreen = dynamic(() => import('./dashboard/dashboard-screen').then((m) => m.DashboardScreen), {
  ssr: false,
  loading: () => <ScreenSkeleton />,
});
const MarketWorkspaceScreen = dynamic(
  () => import('@/components/market-workspace/market-workspace').then((m) => m.MarketWorkspace),
  { ssr: false, loading: () => <ScreenSkeleton /> }
);
const InvestorEyeScreen = dynamic(
  () => import('@/components/investor-eye/investor-eye').then((m) => m.InvestorEyeScreen),
  { ssr: false, loading: () => <ScreenSkeleton /> }
);

import { Newspaper, ArrowLeft } from 'lucide-react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AuroraGlow } from '@/components/layout/aurora-glow';
import { getAgentProvider } from '@/lib/agent/registry';
import { MarketViewsProvider } from '@/lib/dashboard/market-views';
import { useCommandStore } from '@/lib/search/store';
import { useSidebarKeybinds } from '@/hooks/use-sidebar-keybinds';
import { useHydrateI18n, useT } from '@/lib/i18n';
import type { Destination } from '@/lib/search/types';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { TopLoader } from '@/components/ui/top-loader';
import { cn } from '@/lib/utils';

function ScreenSkeleton() {
  // Chunk-load placeholder for next/dynamic screens. Kept minimal and
  // non-competitive with TopLoader (the single real data loader).
  return <TopLoader />;
}

function StockChatContent() {
  // Hydrate interface language + accessibility prefs from localStorage once.
  useHydrateI18n();
  const t = useT();
  const [activeTab, setActiveTab] = useState<AppTab>('chat');
  const [query, setQuery] = useState('');
  const [selectedChartSymbol, setSelectedChartSymbol] = useState('AAPL');
  const [discoveryMarket, setDiscoveryMarket] = useState<string | undefined>(undefined);
  // Symbol pinned into the news tab by global search ("SYMBOL news").
  const [newsSymbol, setNewsSymbol] = useState<string | undefined>(undefined);
  // Symbol pre-filling the screener search ("SYMBOL screener").
  const [discoverySymbol, setDiscoverySymbol] = useState<string | undefined>(undefined);
  
  // Conversations states
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  
  const [mounted, setMounted] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [navHistory, setNavHistory] = useState<AppTab[]>(['chat']);
  const navHistoryRef = useRef(navHistory);
  navHistoryRef.current = navHistory;
  // Section requested by a `settings.<section>` palette subroute.
  const [settingsSection, setSettingsSection] = useState<SectionId | undefined>(undefined);
  // Optional block within the section, e.g. `settings.market#priority`.
  const [settingsAnchor, setSettingsAnchor] = useState<string | undefined>(undefined);

  useEffect(() => {
    setMounted(true);
  }, []);

  // User-assigned F1–F12 shortcuts open their sidebar tab anywhere in the app.
  useSidebarKeybinds(setActiveTab);

  // Keep-alive tabs: a tab mounts on first visit and stays mounted (hidden
  // with display:none) after that. Boot mounts ONLY the initial tab, so we
  // keep the old boot behavior (one screen fetching, no mount-all race),
  // while revisits are instant — no chunk reload, no refetch, no loader.
  const [visited, setVisited] = useState<Set<AppTab>>(() => new Set(['chat']));
  useEffect(() => {
    setVisited(prev => (prev.has(activeTab) ? prev : new Set(prev).add(activeTab)));
  }, [activeTab]);

  useEffect(() => {
    setNavHistory((prev) => recordVisit(prev, activeTab));
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

  // Global command center → tab navigation. Consumes destinations dispatched
  // by the ⌘K search bar and applies them to the SPA's activeTab state machine.
  useEffect(() => {
    const apply = (dest: Destination) => {
      if (dest.params?.action === 'new-chat') {
        handleNewChat();
      }
      if (dest.params?.symbol) {
        setSelectedChartSymbol(dest.params.symbol.toUpperCase());
        // A symbol on the news tab pins the feed to that ticker instead of
        // just loading it into the chart.
        if (dest.tab === 'news') setNewsSymbol(dest.params.symbol.toUpperCase());
        // `focus: 'chart'` is the screener pivot — pre-fill its search box.
        if (dest.tab === 'discovery' && dest.params.focus === 'chart') {
          setDiscoverySymbol(dest.params.symbol.toUpperCase());
        }
      }
      if (dest.params?.fund) {
        useCommandStore.setState({ pendingFundId: dest.params.fund });
      }
      if (dest.params?.prompt) {
        handleNewChat();
        setQuery(dest.params.prompt);
      }
      if (dest.params?.market) {
        useCommandStore.setState({ pendingMarket: dest.params.market });
        setDiscoveryMarket(dest.params.market);
      }
      // Sub-view routing: `subroute` (e.g. 'economics.calendar', 'journal.analytics')
      // is published to the target screen via the command store, with an optional
      // `focus` target. Screens consume it with the `useSubroute` hook.
      if (dest.subroute) {
        const sub = dest.subroute.split('.').slice(1).join('.') || dest.subroute;
        useCommandStore.getState().requestSubroute(dest.tab, sub, dest.params?.focus);
      }
      // Settings has no tab screen — it is a modal. Route there instead of
      // switching to a tab that renders nothing.
      if (dest.tab === 'settings') {
        const raw = dest.subroute?.split('.')[1];
        const sec = raw?.split('#')[0];
        const anchor = raw?.split('#')[1];
        if (sec) setSettingsSection(sec as SectionId);
        setSettingsAnchor(anchor);
        setSettingsOpen(true);
        return;
      }
      if (dest.tab === 'chart') {
        // Chart needs a symbol; default to the last selected one.
        setActiveTab('chart');
      } else {
        setActiveTab(dest.tab);
      }
      if (dest.deepLink) {
        try { window.history.pushState(null, '', dest.deepLink); } catch { /* ignore */ }
      }
    };

    const check = () => {
      const dest = useCommandStore.getState().consumeDestination();
      if (dest) apply(dest);
    };

    check();
    const unsub = useCommandStore.subscribe((state, prev) => {
      if (state.pendingDestination !== prev.pendingDestination && state.pendingDestination) check();
    });
    return unsub;
  }, [mounted]);

  // Workspace panels dispatch `be:navigate` to switch the SPA tab (e.g. the
  // Screener panel links out to the full screener tab).
  useEffect(() => {
    const onNavigate = (e: Event) => {
      const tab = (e as CustomEvent<{ tab?: string }>).detail?.tab;
      if (tab) setActiveTab(tab as AppTab);
    };
    window.addEventListener('be:navigate', onNavigate);
    return () => window.removeEventListener('be:navigate', onNavigate);
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

  const chatRootRef = useRef<HTMLDivElement>(null);
  const appRootRef = useRef<HTMLDivElement>(null);
  const handleBack = () => {
    if (settingsOpen || mobileMenuOpen) return;
    const target = backTarget(navHistoryRef.current);
    if (!target) return;
    navHistoryRef.current = target.history;
    setNavHistory(target.history);
    setActiveTab(target.tab);
  };
  usePageShortcuts(chatRootRef, [
    { id: 'chat.new', label: 'New chat', keys: 'Shift+N', run: handleNewChat, enabled: activeTab === 'chat' && !settingsOpen && !mobileMenuOpen },
  ]);
  usePageShortcuts(appRootRef, [
    { id: 'nav.back', label: 'Back', keys: 'Alt+ArrowLeft', run: handleBack, enabled: navHistory.length > 1 && !settingsOpen && !mobileMenuOpen },
  ]);

  const handleChartTicker = (symbol?: string) => {
    if (symbol) {
      setSelectedChartSymbol(symbol);
    }
    setActiveTab('chart');
  };

  // ── Aurora glow ─────────────────────────────────────────────────────────
  // The app-wide market-state indicator is mounted via <AuroraGlow>, which owns
  // the sentiment subscription + user palette and renders the masked top glow.
  // Fullscreen mounts its own copy (it portals to <body>, above the shell).

  return (
    <TooltipProvider delay={0}>
    <div ref={appRootRef} className="relative flex flex-col md:flex-row h-[100dvh] w-full bg-background text-foreground font-sans selection:bg-primary/30 overflow-hidden">
      {/* Keyboard users can jump straight past the sidebar to the main content. */}
      <a href="#main-content" className="skip-to-content">
        {t('a11y.skipToContent')}
      </a>
      {/* Aurora full-viewport top glow — reflects blended market + news sentiment */}
      <AuroraGlow />

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

      <div className="flex-1 flex flex-col relative z-10 overflow-hidden glass-card min-w-0 h-full before:pointer-events-none before:absolute before:inset-x-0 before:top-0 before:h-px before:bg-gradient-to-r before:from-transparent before:via-white/60 dark:before:via-white/10 before:to-transparent">
        <TopBar 
          onToggleMenu={() => setMobileMenuOpen(true)}
          activeTab={activeTab}
        />

        <div id="main-content" className="flex-1 overflow-y-auto relative w-full h-full z-10" tabIndex={-1}>
          {/* Keep-alive tabs: a tab mounts on first visit (visited set) and
              then stays mounted hidden — revisits are instant with no chunk
              reload, no refetch, no loader flash. Unvisited tabs render
              nothing, preserving the old single-screen boot behavior. */}
          {visited.has('dashboard') && (
            <div data-keepalive-panel className={cn('w-full h-full', activeTab === 'dashboard' ? '' : 'hidden')}>
              <div className="flex-1 w-full px-4 md:px-8 py-8">
                <MarketViewsProvider>
                  <DashboardScreen />
                </MarketViewsProvider>
              </div>
            </div>
          )}

          {visited.has('market-workspace') && (
            <div className={cn('w-full', activeTab === 'market-workspace' ? '' : 'hidden')}>
              <div className="w-full px-3 md:px-5 py-4">
                <MarketWorkspaceScreen />
              </div>
            </div>
          )}

          {visited.has('investor-eye') && (
            <div className={cn('w-full h-full', activeTab === 'investor-eye' ? '' : 'hidden')}>
              <InvestorEyeScreen />
            </div>
          )}

          {visited.has('chat') && (
            <div ref={chatRootRef} data-keyboard-scope="Chat" className={activeTab === 'chat' ? 'w-full h-full' : 'hidden'}>
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
              <div className="flex-1 w-full px-4 md:px-8 py-8 overflow-y-auto h-full pb-20">
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
                    symbol={newsSymbol}
                  />
                </div>
              </div>
            </div>
          )}

          {visited.has('discovery') && (
            <div className={cn('w-full h-full', activeTab === 'discovery' ? '' : 'hidden')}>
              <div className="flex-1 w-full px-4 md:px-8 py-8">
                <div className="animate-fade-in-up w-full h-full">
                  <MarketOverviewScreen
                    key={`${discoveryMarket ?? 'default'}:${discoverySymbol ?? ''}`}
                    market={discoveryMarket}
                    initialSymbol={discoverySymbol}
                    onAnalyzeTicker={(t: string, customCtx?: string) => handleInjectPrompt(t, 'research', customCtx)}
                    onSelectChartSymbol={(sym) => {
                      setSelectedChartSymbol(sym);
                      setActiveTab('chart');
                    }}
                    embedded={false}
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
              <div className="flex-1 w-full px-4 md:px-8 py-8">
                <PortfolioScreen />
              </div>
            </div>
          )}

          {visited.has('journal') && (
            <div className={cn('w-full h-full', activeTab === 'journal' ? '' : 'hidden')}>
              <div className="flex-1 w-full px-4 md:px-8 py-8">
                <JournalScreen />
              </div>
            </div>
          )}

          {visited.has('chart') && (
            <div className={cn('w-full h-full', activeTab === 'chart' ? '' : 'hidden')}>
              <div className="flex-1 w-full px-4 md:px-8 py-6 h-full">
                <button
                  onClick={() => setActiveTab('discovery')}
                  className="mb-3 inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-primary border border-border/40 hover:border-primary/40 bg-accent/30 hover:bg-accent/60 rounded-xl px-3 py-1.5 transition-all cursor-pointer"
                >
                  <ArrowLeft size={13} /> Back to Market Screener
                </button>
                <ChartWidget symbol={selectedChartSymbol} className="h-full" />
              </div>
            </div>
          )}
        </div>
      </div>

      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="w-[calc(100%-2rem)] max-w-6xl sm:max-w-6xl h-[min(90dvh,880px)] p-0 gap-0 overflow-hidden rounded-2xl border border-white/10 glass-card-strong shadow-2xl text-foreground">
          <DialogTitle className="sr-only">{t('common.settings')}</DialogTitle>
          {/* Keyed so a palette `settings.<section>` request remounts into the
              requested section even while the modal is already open. */}
          <Settings
            key={`${settingsSection ?? 'default'}:${settingsAnchor ?? ''}`}
            initialSection={settingsSection}
            initialAnchor={settingsAnchor}
          />
        </DialogContent>
      </Dialog>
    </div>
    </TooltipProvider>
  );
}

export function StockChat() {
  return <StockChatContent />;
}
