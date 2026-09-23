'use client';

import { useState, useEffect, useRef } from 'react';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import dynamic from 'next/dynamic';
import { Sidebar, AppTab, Conversation } from '@/components/layout/sidebar';
import { backTarget, recordVisit } from '@/lib/navigation-history';
import { TopBar } from '@/components/layout/top-bar';
import { EmptyState } from '@/components/chat/empty-state';
import { ChatHistory } from '@/components/chat/chat-history';
import { ChatInput } from '@/components/chat/chat-input';
import { ChatDock } from '@/components/chat/chat-dock';
import { SessionBar } from '@/components/chat/session-bar';
import { CheckpointBar } from '@/components/chat/checkpoint-bar';
import { useSession } from '@/lib/chat/use-session';
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
const SkillsScreen = dynamic(
  () => import('@/components/screens/skills/skills-screen').then((m) => m.SkillsScreen),
  { ssr: false, loading: () => <ScreenSkeleton /> }
);
const EclipseMemoryScreen = dynamic(
  () => import('@/components/screens/eclipse-memory/eclipse-memory-screen').then((m) => m.EclipseMemoryScreen),
  { ssr: false, loading: () => <ScreenSkeleton /> }
);

import { Newspaper, ArrowLeft } from 'lucide-react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AuroraGlow } from '@/components/layout/aurora-glow';
import { useAgentRun } from '@/lib/agent/use-agent-run';
import { clientIsOperator } from '@/lib/harness/skills-browser';
import type { AssistantTurn } from '@/lib/agent/response-model';
import { turnText } from '@/lib/agent/response-model';
import { MarketViewsProvider } from '@/lib/dashboard/market-views';
import { useCommandStore } from '@/lib/search/store';
import { useSidebarKeybinds } from '@/hooks/use-sidebar-keybinds';
import { sound } from '@/lib/sounds';
import { useHydrateI18n, useT } from '@/lib/i18n';
import { useHydrateTheme, useThemeStore } from '@/lib/theme';
import type { Destination } from '@/lib/search/types';
import { destinationToQuery, parseDeepLink } from '@/lib/search/deep-link';
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
  // Hydrate the centralized theme (branding/fonts/colors) and apply its tokens.
  useHydrateTheme();
  const t = useT();
  // Full-screen theme preview (Settings › Customization) hides the modal so the
  // real app can be auditioned; the panel stays mounted to keep its draft.
  const themePreviewMode = useThemeStore((s) => s.previewMode);
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
  // Bumped when a run finishes so the session bar re-lists output files.
  const [sessionRefreshKey, setSessionRefreshKey] = useState(0);
  // True while the agent is working — swaps the submit arrow for a pause button.
  const [agentBusy, setAgentBusy] = useState(false);
  // Shared session controller: the composer's "+" uploads and the bar displays.
  const sessionController = useSession(activeConversationId, sessionRefreshKey);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // The one place a turn's streaming lifecycle lives. The hook reports the
  // AssistantTurn; we map it onto the message store below. `turnSinkRef` is set
  // per-run so the callback targets the turn being written (state closures would
  // otherwise hold pre-send values after each await).
  const turnSinkRef = useRef<((turn: AssistantTurn) => void) | null>(null);
  // Prevents a duplicate submit landing before React re-renders `agentBusy`.
  const runInFlightRef = useRef(false);
  const agentRun = useAgentRun({
    onTurn: (turn) => turnSinkRef.current?.(turn),
  });
  useEffect(() => {
    setAgentBusy(agentRun.active);
  }, [agentRun.active]);

  // Refs mirror the two pieces of state an async send handler reads AFTER an
  // await. React state setters do not update the render closure, so reading
  // `conversations` there returns the pre-send value and a reply to a
  // just-created chat would be silently dropped. The refs are kept current
  // synchronously by every write below.
  const conversationsRef = useRef<Conversation[]>([]);
  conversationsRef.current = conversations;
  const activeConversationIdRef = useRef<string | null>(null);
  activeConversationIdRef.current = activeConversationId;
  
  const [mounted, setMounted] = useState(false);
  // True once the boot deep link has been applied, so the URL-sync effect never
  // overwrites it before the tab/symbol state settles.
  const bootDoneRef = useRef(false);
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

  // Deep-link boot + history: /?tab=portfolio or /?tab=chart&symbol=AAPL opens
  // that page directly. Powers Ctrl/Cmd-click, middle-click and "open in new
  // tab" from the sidebar, command palette and screener. Also re-applies on
  // browser back/forward so the URL stays the source of truth.
  //
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

    // Boot from the URL (deep link / refresh / new tab).
    try {
      const boot = parseDeepLink(window.location.search);
      if (boot) apply(boot);
    } catch { /* ignore malformed URLs */ }
    bootDoneRef.current = true;

    // Browser back/forward re-applies the URL's destination.
    const onPopState = () => {
      try {
        const dest = parseDeepLink(window.location.search);
        if (dest) apply(dest);
      } catch { /* ignore malformed URLs */ }
    };
    window.addEventListener('popstate', onPopState);

    check();
    const unsub = useCommandStore.subscribe((state, prev) => {
      if (state.pendingDestination !== prev.pendingDestination && state.pendingDestination) check();
    });
    return () => {
      unsub();
      window.removeEventListener('popstate', onPopState);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted]);

  // Keep the URL in sync with the active tab so a refresh/share opens the same
  // page and Ctrl/Cmd-click has a real href to target. `replaceState` avoids
  // polluting history on every in-app switch. When the current URL already
  // points at the same tab, its subroute/params are preserved (e.g. a settings
  // section or the chart's symbol) so the deep link survives the sync.
  useEffect(() => {
    if (!mounted || !bootDoneRef.current) return;
    try {
      const current = parseDeepLink(window.location.search);
      let next: Destination;
      if (current && current.tab === activeTab) {
        next = current;
        if (activeTab === 'chart' && selectedChartSymbol) {
          next = { tab: 'chart', params: { ...current.params, symbol: selectedChartSymbol } };
        }
      } else if (activeTab === 'chart') {
        next = { tab: 'chart', params: { symbol: selectedChartSymbol } };
      } else {
        next = { tab: activeTab };
      }
      const query = destinationToQuery(next);
      if (window.location.search.slice(1) !== query) {
        window.history.replaceState(null, '', `${window.location.pathname}?${query}`);
      }
    } catch { /* ignore malformed URLs */ }
  }, [mounted, activeTab, selectedChartSymbol]);


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
        conversationsRef.current = parsed;
        setConversations(parsed);
        if (parsed.length > 0) {
          activeConversationIdRef.current = parsed[0].id;
          setActiveConversationId(parsed[0].id);
          setMessages(parsed[0].messages);
        } else {
          activeConversationIdRef.current = null;
          setActiveConversationId(null);
          setMessages([]);
        }
      } catch (err) {
        console.error('Error loading conversations:', err);
      }
    } else {
      conversationsRef.current = [];
      setConversations([]);
      activeConversationIdRef.current = null;
      setActiveConversationId(null);
      setMessages([]);
    }
  }, [mounted]);

  const saveConversations = (updated: Conversation[]) => {
    conversationsRef.current = updated;
    setConversations(updated);
    const key = 'chats_guest';
    localStorage.setItem(key, JSON.stringify(updated));
  };

  const handleSelectConversation = (id: string) => {
    activeConversationIdRef.current = id;
    setActiveConversationId(id);
    const chat = conversationsRef.current.find(c => c.id === id);
    if (chat) {
      setMessages(chat.messages);
    }
  };

  const handleNewChat = () => {
    activeConversationIdRef.current = null;
    setActiveConversationId(null);
    setMessages([]);
  };

  const handleDeleteConversation = (id: string) => {
    const updated = conversationsRef.current.filter(c => c.id !== id);
    saveConversations(updated);
    if (activeConversationIdRef.current === id) {
      if (updated.length > 0) {
        activeConversationIdRef.current = updated[0].id;
        setActiveConversationId(updated[0].id);
        setMessages(updated[0].messages);
      } else {
        activeConversationIdRef.current = null;
        setActiveConversationId(null);
        setMessages([]);
      }
    }
  };

  const addMessageToActiveChat = (userMsg: Message) => {
    // Read through the refs, not the closure: two sends in the same tick (or a
    // send followed by an injected prompt) must see each other's writes.
    let currentId = activeConversationIdRef.current;
    let updatedConvs = [...conversationsRef.current];

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
      activeConversationIdRef.current = currentId;
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
      } else {
        // Active id points at a conversation that no longer exists (e.g. it was
        // deleted) — start a fresh one instead of dropping the message.
        currentId = 'chat_' + Date.now();
        const newChat: Conversation = {
          id: currentId,
          title: userMsg.content.slice(0, 24),
          messages: [userMsg],
          timestamp: Date.now()
        };
        updatedConvs = [newChat, ...updatedConvs];
        activeConversationIdRef.current = currentId;
        setActiveConversationId(currentId);
        setMessages([userMsg]);
      }
    }

    // Keep the ref in lockstep so an immediately-following append sees this.
    conversationsRef.current = updatedConvs;
    saveConversations(updatedConvs);
    return currentId;
  };

  const appendAssistantReply = (chatId: string, replyMsg: Message, persist = true) => {
    // IMPORTANT: use the ref, not `conversations`. This runs after `await`, so
    // the closure holds pre-send state and a reply to a brand-new chat would
    // otherwise be silently discarded.
    const updatedConvs = [...conversationsRef.current];
    const idx = updatedConvs.findIndex(c => c.id === chatId);
    if (idx === -1) {
      // Never drop a reply: recreate the conversation if it vanished.
      const recovered: Conversation = {
        id: chatId,
        title: replyMsg.content.slice(0, 24),
        messages: [replyMsg],
        timestamp: Date.now(),
      };
      const next = [recovered, ...updatedConvs];
      conversationsRef.current = next;
      if (persist) saveConversations(next);
      setMessages([replyMsg]);
      return;
    }
    const chat = updatedConvs[idx];
    const newMsgList = [...chat.messages, replyMsg];
    updatedConvs[idx] = {
      ...chat,
      messages: newMsgList,
      timestamp: Date.now()
    };
    conversationsRef.current = updatedConvs;
    if (persist) saveConversations(updatedConvs);
    if (activeConversationIdRef.current === chatId) {
      setMessages(newMsgList);
    }
  };

  /**
   * Swap an in-flight placeholder for its final message (same position).
   *
   * `persist=false` updates React state only. Streaming calls this on every
   * frame, and serializing the whole transcript to localStorage ~60×/s is the
   * single hottest write in the chat; persistence is deferred to the terminal
   * frame where it actually matters.
   */
  const replaceAssistantReply = (chatId: string, placeholderId: string, replyMsg: Message, persist = true) => {
    const updatedConvs = [...conversationsRef.current];
    const idx = updatedConvs.findIndex(c => c.id === chatId);
    if (idx === -1) {
      appendAssistantReply(chatId, replyMsg, persist);
      return;
    }
    const chat = updatedConvs[idx];
    const newMsgList = chat.messages.map(m => (m.id === placeholderId ? replyMsg : m));
    updatedConvs[idx] = { ...chat, messages: newMsgList, timestamp: Date.now() };
    conversationsRef.current = updatedConvs;
    if (persist) saveConversations(updatedConvs);
    if (activeConversationIdRef.current === chatId) {
      setMessages(newMsgList);
    }
  };

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim() || agentBusy) return;

    const userText = query;
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: userText };
    setQuery('');
    
    const chatId = addMessageToActiveChat(userMsg);
    await runAgent(chatId, userText, userMsg);
  };

  /**
   * Run one turn through the harness and track cancellation. EVERY message goes
   * through the harness, so the chat IS the Eclipse Agent (system prompt + JDdS
   * tools + persisted run). History is read from the ref (not state) because
   * this runs after `await`.
   */
  const runAgent = async (chatId: string, userText: string, userMsg: Message) => {
    // Guard against a duplicate submit landing before the state update.
    if (runInFlightRef.current) return;
    runInFlightRef.current = true;

    const existing = conversationsRef.current.find((c) => c.id === chatId)?.messages ?? [userMsg];
    // Drop empty turns (cancelled/failed replies persist as ""). They carry no
    // context for the model and the front door would otherwise reject the run.
    const history: { role: 'user' | 'assistant'; content: string }[] = existing
      .slice(0, -1)
      .filter((m) => m.content.trim().length > 0)
      .map((m) => ({ role: m.role, content: m.content }));

    // A placeholder assistant turn. Its fields are filled by the shared run
    // hook (status, streamed text, activities); until the first event the turn
    // reads as "the agent is working on this reply".
    const placeholderId = (Date.now() + 1).toString();
    appendAssistantReply(chatId, {
      id: placeholderId,
      role: 'assistant',
      content: '',
      status: 'queued',
      activities: [],
    });

    // Route the hook's turn updates into this exact message. Streaming frames
    // update state only; the transcript is persisted once when the run reaches
    // a terminal state (see the finally block), so a long stream does not
    // serialize the whole conversation to localStorage ~60×/second.
    turnSinkRef.current = (turn) => {
      replaceAssistantReply(chatId, placeholderId, {
        id: placeholderId,
        role: 'assistant',
        content: turnText(turn),
        status: turn.status,
        activities: turn.activities,
        research: turn.research,
        error: turn.error,
      }, turn.done);
    };

    setAgentBusy(true);
    sound.tick();

    try {
      const finalTurn = await agentRun.start({ history, userText, chatId });
      setSessionRefreshKey((k) => k + 1);
      if (finalTurn.status === 'completed' && (finalTurn.finalText || finalTurn.text)) sound.success();
      else sound.tick();
    } catch (err) {
      // The hook records the error on the turn; ensure the message reflects it
      // even if the sink was cleared.
      replaceAssistantReply(chatId, placeholderId, {
        id: placeholderId,
        role: 'assistant',
        content: '',
        status: 'error',
        error: { message: err instanceof Error ? err.message : String(err) },
      });
      sound.error();
    } finally {
      turnSinkRef.current = null;
      runInFlightRef.current = false;
      setAgentBusy(false);
      // Persist the terminal transcript once (covers cancel/abort paths too).
      saveConversations(conversationsRef.current);
    }
  };

  /** Stop the in-flight run (cooperative cancel in the Python runtime). */
  const handleCancel = async () => {
    sound.tick();
    agentRun.cancel();
  };

  /** Record a user's rating on an assistant turn (persisted with the message). */
  const handleFeedback = (id: string, feedback: 'up' | 'down') => {
    const chatId = activeConversationIdRef.current;
    if (!chatId) return;
    const updated = conversationsRef.current.map((c) => {
      if (c.id !== chatId) return c;
      return {
        ...c,
        messages: c.messages.map((m) =>
          m.id === id ? { ...m, feedback: m.feedback === feedback ? undefined : feedback } : m,
        ),
      };
    });
    saveConversations(updated);
    const chat = updated.find((c) => c.id === chatId);
    if (chat) setMessages(chat.messages);
  };

  /**
   * Re-run the prompt that produced an assistant turn. Used by the message
   * toolbar's Retry/Regenerate. It reuses the edit path: truncate at that turn's
   * preceding user message and resend it.
   */
  const handleRetryMessage = (assistantId: string) => {
    const chatId = activeConversationIdRef.current;
    if (!chatId) return;
    const chat = conversationsRef.current.find((c) => c.id === chatId);
    if (!chat) return;
    const idx = chat.messages.findIndex((m) => m.id === assistantId);
    if (idx < 1) return;
    // Find the user prompt this assistant turn answered.
    let userId = -1;
    for (let i = idx - 1; i >= 0; i -= 1) {
      if (chat.messages[i].role === 'user') { userId = i; break; }
    }
    if (userId === -1) return;
    handleEditMessage(chat.messages[userId].id, chat.messages[userId].content);
  };

  /**
   * Edit a previously-sent prompt: drop that message and everything after it
   * (the thread is a linear transcript, so later turns depended on it), then
   * re-send the edited text. This is the standard "edit and branch" behavior
   * without introducing branching state.
   */
  const handleEditMessage = (id: string, content: string) => {
    const chatId = activeConversationIdRef.current;
    if (!chatId) return;
    const chat = conversationsRef.current.find((c) => c.id === chatId);
    if (!chat) return;

    const idx = chat.messages.findIndex((m) => m.id === id);
    if (idx === -1) return;

    const truncated = chat.messages.slice(0, idx);
    const updatedConvs = conversationsRef.current.map((c) =>
      c.id === chatId ? { ...c, messages: truncated, timestamp: Date.now() } : c
    );
    conversationsRef.current = updatedConvs;
    saveConversations(updatedConvs);
    if (activeConversationIdRef.current === chatId) setMessages(truncated);

    // Re-run the edited prompt through the agent.
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content };
    const newChatId = addMessageToActiveChat(userMsg);
    void runAgent(newChatId, content, userMsg);
  };

  /** Inject a prompt and run it through the Eclipse Agent (the harness) so the
   *  answer is grounded in JDdS tools — never a canned fabricated reply. */
  const runAgentPrompt = async (chatId: string, userText: string) => {
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: userText };
    await runAgent(chatId, userText, userMsg);
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
    void runAgentPrompt(chatId, customContext ? `${customPrompt}\n\nContext data: ${customContext}` : customPrompt);

    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDiscussNews = (news: NewsItem) => {
    setActiveTab('chat');
    const prompt = `Discuss the market implications of: "${news.headline}" for ${news.ticker || 'the market'}.`;

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: prompt };
    const chatId = addMessageToActiveChat(userMsg);
    void runAgentPrompt(chatId, prompt);

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
    <div ref={appRootRef} className="app-page-bg relative flex flex-col md:flex-row h-[100dvh] w-full bg-background text-foreground font-sans selection:bg-primary/30 overflow-hidden">
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
              <div className="w-full h-full flex flex-col items-center justify-between pt-2 md:pt-4 relative min-w-0">
                {messages.length === 0 ? (
                  <EmptyState
                    query={query}
                    setQuery={setQuery}
                    onSend={handleSend}
                    onViewMarketOverview={() => setActiveTab('discovery')}
                    onAttach={() => fileInputRef.current?.click()}
                    busy={agentBusy}
                    onCancel={handleCancel}
                  />
                ) : (
                  <div className="flex-1 flex flex-col items-center w-full min-h-0 relative z-10 overflow-hidden justify-between">
                    <ChatHistory
                      messages={messages}
                      onEditMessage={handleEditMessage}
                      onRetryMessage={handleRetryMessage}
                      onFeedback={handleFeedback}
                    />
                    <div className="w-full px-4 md:px-6 relative group mt-auto shrink-0 pb-1">
                      <ChatInput
                        query={query}
                        setQuery={setQuery}
                        onSend={handleSend}
                        placeholder="Ask a follow-up..."
                        showProvider={false}
                        busy={agentBusy}
                        onCancel={handleCancel}
                        onAttach={() => fileInputRef.current?.click()}
                        attaching={sessionController.busy}
                        contextLabel={sessionController.session && sessionController.session.contextChars > 0
                          ? `${(sessionController.session.contextChars / 1000).toFixed(1)}k / ${(sessionController.session.contextLimitChars / 1000).toFixed(0)}k chars`
                          : undefined}
                        contextFraction={sessionController.session
                          ? sessionController.session.contextChars / sessionController.session.contextLimitChars
                          : 0}
                      />
                      <div className="mt-1.5 flex items-center gap-2">
                        <div className="min-w-0 flex-1">
                          <SessionBar session={sessionController} />
                        </div>
                        <CheckpointBar
                          chatId={activeConversationId}
                          messages={messages}
                          onRestore={(restored) => {
                            setMessages(restored);
                            if (activeConversationId) {
                              const updated = conversationsRef.current.map((c) =>
                                c.id === activeConversationId ? { ...c, messages: restored } : c
                              );
                              saveConversations(updated);
                            }
                          }}
                        />
                      </div>
                    </div>
                  </div>
                )}
                {/* One hidden picker serves the "+" in both the empty state and
                    the running conversation. */}
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    void sessionController.uploadFiles(e.target.files ?? []);
                    e.target.value = '';
                  }}
                />
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

          {visited.has('skills') && (
            <div className={cn('w-full h-full', activeTab === 'skills' ? '' : 'hidden')}>
              <SkillsScreen isOperator={clientIsOperator()} />
            </div>
          )}

          {visited.has('memory') && (
            <div className={cn('w-full h-full', activeTab === 'memory' ? '' : 'hidden')}>
              <EclipseMemoryScreen isOperator={clientIsOperator()} />
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

          {/* App-wide floating assistant — present on every tab except the
              ChatBot (it would be a second composer next to the full chat) and
              while the Settings modal is open. Mounted once here rather than
              per-screen; the dock gates on this panel's own display so it never
              floats over an inactive keep-alive tab. */}
          <ChatDock visible={activeTab !== 'chat' && !settingsOpen} />
        </div>
      </div>

      <Dialog
        open={settingsOpen}
        // While previewing, the floating bar owns exit/apply/discard; ignore any
        // close request (Esc/backdrop) so the mounted panel keeps its draft.
        onOpenChange={(o) => { if (!o && themePreviewMode) return; setSettingsOpen(o); }}
        modal={!themePreviewMode}
      >
        <DialogContent
          overlayClassName={cn(themePreviewMode && 'hidden')}
          className={cn(
            'w-[calc(100%-2rem)] max-w-6xl sm:max-w-6xl h-[min(90dvh,880px)] p-0 gap-0 overflow-hidden rounded-2xl border border-white/10 glass-card-strong shadow-2xl text-foreground',
            // Full-screen preview: keep the panel MOUNTED (draft state survives)
            // but hidden, so the real app is visible behind the floating bar.
            themePreviewMode && 'hidden',
          )}
        >
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
