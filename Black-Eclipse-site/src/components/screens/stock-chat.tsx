'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import { usePageShortcuts, useKeyboardShortcutsStore } from '@/hooks/use-page-shortcuts';
import dynamic from 'next/dynamic';
import { Sidebar, AppTab, Conversation } from '@/components/layout/sidebar';
import { TerminalDock } from '@/components/terminal/terminal-dock';
import { AgentWorkspace } from '@/components/agent-workspace/workspace';
import { useTerminalShell } from '@/hooks/use-terminal-shell';
import { backTarget, recordVisit } from '@/lib/navigation-history';
import { TopBar } from '@/components/layout/top-bar';
import { EmptyState } from '@/components/chat/empty-state';
import { ChatHistory } from '@/components/chat/chat-history';
import { ChatInput } from '@/components/chat/chat-input';
import { ApprovalCard } from '@/components/chat/approval-card';
import { ChatDock } from '@/components/chat/chat-dock';
import { SessionBar } from '@/components/chat/session-bar';
import { CheckpointBar } from '@/components/chat/checkpoint-bar';
import { ChatWordmark } from '@/components/chat/chat-wordmark';
import { useSession, mergeAttachmentChips } from '@/lib/chat/use-session';
import { CONVERSATIONS_STORAGE_KEY, normalizeConversations } from '@/lib/chat/chat-organization';
import { useChatOrganization } from '@/lib/chat/use-chat-organization';
import { useHydrateBackground } from '@/lib/backgrounds';
import { useHydrateChatAppearance } from '@/lib/chat/appearance';
import { Message } from '@/types/chat';
import { useWorkspaceStore } from '@/lib/agent-workspace/store';
import { restoreWorkspaceForChat } from '@/lib/agent-workspace/restore';

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
// Settings: code-split, but warmed during idle so the first open paints
// instantly (cold chunk fetch + mount was the slow/blank-load cause).
const settingsImport = () => import('./settings');
const Settings = dynamic(() => settingsImport().then((m) => m.Settings), { ssr: false, loading: () => <ScreenSkeleton /> });
import type { SectionId } from './settings';
if (typeof window !== 'undefined') {
  const idle = (window as Window & { requestIdleCallback?: (cb: () => void) => number }).requestIdleCallback;
  idle ? idle(() => void settingsImport()) : window.setTimeout(() => void settingsImport(), 2000);
}
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
const ArtifactsScreen = dynamic(
  () => import('@/components/screens/artifacts/artifacts-screen').then((m) => m.ArtifactsScreen),
  { ssr: false, loading: () => <ScreenSkeleton /> }
);
const TasksScreen = dynamic(
  () => import('@/components/screens/tasks/tasks-screen').then((m) => m.TasksScreen),
  { ssr: false, loading: () => <ScreenSkeleton /> }
);
const UiBuilderScreen = dynamic(
  () => import('@/components/screens/ui-builder/ui-builder-screen').then((m) => m.UiBuilderScreen),
  { ssr: false, loading: () => <ScreenSkeleton /> }
);
const PagesScreen = dynamic(
  () => import('@/components/screens/pages/pages-screen').then((m) => m.PagesScreen),
  { ssr: false, loading: () => <ScreenSkeleton /> }
);
const BacktestScreen = dynamic(
  () => import('@/components/screens/backtest/backtest-screen').then((m) => m.BacktestScreen),
  { ssr: false, loading: () => <ScreenSkeleton /> }
);
const ResearchDataScreen = dynamic(
  () => import('@/components/screens/research-data/research-data-screen').then((m) => m.ResearchDataScreen),
  { ssr: false, loading: () => <ScreenSkeleton /> }
);
import { Newspaper, ArrowLeft } from '@/lib/icons';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AuroraGlow } from '@/components/layout/aurora-glow';
import { MarketRegimeControl } from '@/components/layout/market-regime-control';
import { useAgentRun } from '@/lib/agent/use-agent-run';
import { useChatModel } from '@/lib/agent/use-chat-model';
import { useReasoningEffort } from '@/lib/agent/use-reasoning-effort';
import { clientIsOperator } from '@/lib/harness/skills-browser';
import { turnText, type AssistantTurn } from '@/lib/agent/response-model';
import { MarketViewsProvider } from '@/lib/dashboard/market-views';
import { useCommandStore } from '@/lib/search/store';
import { useRegimeScopeStore } from '@/lib/regime/store';
import { useSidebarKeybinds } from '@/hooks/use-sidebar-keybinds';
import { sound } from '@/lib/sounds';
import { useHydrateI18n, useT } from '@/lib/i18n';
import { useHydrateTheme, useThemeStore } from '@/lib/theme';
import type { Destination } from '@/lib/search/types';
import { destinationToQuery, parseDeepLink } from '@/lib/search/deep-link';
import { loadGeneralPrefs, recordLastTab, resolveStartTab } from '@/lib/general-prefs';
import { hasBlockingKeyboardDialog, isKeyboardEventAvailable, matchesShortcut } from '@/lib/keyboard';
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
  // Hydrate the app background (wallpaper; ChatBot page only).
  useHydrateBackground();
  // Hydrate the ChatBot conversation font (ChatBot page only).
  useHydrateChatAppearance();
  const t = useT();
  // Full-screen theme preview (Settings › Customization) hides the modal so the
  // real app can be auditioned; the panel stays mounted to keep its draft.
  const themePreviewMode = useThemeStore((s) => s.previewMode);
  // Boot tab: Settings › General can pin a start screen (or "Last screen"). The
  // URL deep link below always overrides this when one is present.
  const [activeTab, setActiveTab] = useState<AppTab>(() => resolveStartTab(loadGeneralPrefs()) ?? 'chat');
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
  // The composer container the approval card floats above (portaled to <body>).
  // Held in state (not a ref) so the card re-measures once the node mounts.
  const [composerEl, setComposerEl] = useState<HTMLDivElement | null>(null);

  // Visible attachment chips at the composer: pending + the session's saved
  // context files, de-duplicated.
  const attachmentChips = useMemo(
    () => mergeAttachmentChips(
      sessionController.pending,
      (sessionController.session?.files ?? []).filter((f) => f.kind === 'context'),
    ),
    [sessionController.pending, sessionController.session],
  );

  const handleRemoveAttachment = (name: string) => {
    if (sessionController.pending.some((p) => p.name === name)) {
      sessionController.removePending(name);
      return;
    }
    const file = sessionController.session?.files.find((f) => f.kind === 'context' && f.name === name);
    if (file) void sessionController.removeFile(file);
  };

  // The one place a turn's streaming lifecycle lives. The hook reports the
  // AssistantTurn; we map it onto the message store below. `turnSinkRef` is set
  // per-run so the callback targets the turn being written (state closures would
  // otherwise hold pre-send values after each await).
  const turnSinkRef = useRef<((turn: AssistantTurn) => void) | null>(null);
  // Prevents a duplicate submit landing before React re-renders `agentBusy`.
  const runInFlightRef = useRef(false);
  const agentRun = useAgentRun({ onTurn: (turn) => turnSinkRef.current?.(turn) });
  const chatModel = useChatModel(); // the composer's real, persisted model choice
  const reasoningEffort = useReasoningEffort(); // per-question "model intelligence"
  useEffect(() => { setAgentBusy(agentRun.active); }, [agentRun.active]);

  // The action the agent is blocked on, if any. Sourced from the live turn and
  // falling back to the last persisted assistant message, so the card survives a
  // transcript re-render mid-run (the turn sink writes it onto the message).
  const pendingApproval = useMemo(
    () => agentRun.turn.pendingApproval
      ?? [...messages].reverse().find((m) => m.role === 'assistant' && m.pendingApproval)?.pendingApproval,
    [agentRun.turn.pendingApproval, messages],
  );

  // Refs mirror the two pieces of state an async send handler reads AFTER an
  // await. React state setters do not update the render closure, so reading
  // `conversations` there returns the pre-send value and a reply to a
  // just-created chat would be silently dropped. The refs are kept current
  // synchronously by every write below.
  const conversationsRef = useRef<Conversation[]>([]);
  conversationsRef.current = conversations;
  const activeConversationIdRef = useRef<string | null>(null);
  activeConversationIdRef.current = activeConversationId;
  // Mirrors the active tab for the window-level focus-mode listener below.
  const activeTabRef = useRef<AppTab>(activeTab);
  activeTabRef.current = activeTab;
  
  const [mounted, setMounted] = useState(false);
  // True once the boot deep link has been applied, so the URL-sync effect never
  // overwrites it before the tab/symbol state settles.
  const bootDoneRef = useRef(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Focus mode: a presentation-only "zen" view of the chat — hides the header
  // and sidebar and parks the transcript + composer in a centered column.
  // Scoped to the chat tab and the Ctrl+Alt+X shortcut.
  const [focusMode, setFocusMode] = useState(false);
  const [navHistory, setNavHistory] = useState<AppTab[]>(['chat']);
  const navHistoryRef = useRef(navHistory);
  navHistoryRef.current = navHistory;
  // Section requested by a `settings.<section>` palette subroute.
  const [settingsSection, setSettingsSection] = useState<SectionId | undefined>(undefined);
  // Optional block within the section, e.g. `settings.market#priority`.
  const [settingsAnchor, setSettingsAnchor] = useState<string | undefined>(undefined);

  useEffect(() => { setMounted(true); }, []);

  // User-assigned F1–F12 shortcuts open their sidebar tab anywhere in the app.
  useSidebarKeybinds(setActiveTab);

  // Keep-alive tabs: a tab mounts on first visit and stays mounted (hidden
  // with display:none) after that. Boot mounts ONLY the initial tab, so we
  // keep the old boot behavior (one screen fetching, no mount-all race),
  // while revisits are instant — no chunk reload, no refetch, no loader.
  const [visited, setVisited] = useState<Set<AppTab>>(() => new Set([activeTab]));
  useEffect(() => {
    setVisited(prev => (prev.has(activeTab) ? prev : new Set(prev).add(activeTab)));
  }, [activeTab]);

  useEffect(() => {
    setNavHistory((prev) => recordVisit(prev, activeTab));
    // Remember the last visited tab so `startScreen: 'history'` can resume it.
    if (mounted) recordLastTab(activeTab);
  }, [activeTab, mounted]);

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
      // Market Regime is a top-bar panel, not a tab — open it and stop, so a
      // "market regime" search never switches the tab away.
      if (dest.params?.action === 'open-regime') {
        useRegimeScopeStore.getState().setPanelOpen(true);
        return;
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
      const detail = (e as CustomEvent<{ tab?: string; section?: string }>).detail;
      // Settings is a modal, not a tab: open it at the requested section instead
      // of switching to a tab that renders nothing.
      if (detail?.tab === 'settings') {
        if (detail.section) setSettingsSection(detail.section as SectionId);
        setSettingsOpen(true);
        return;
      }
      if (detail?.tab) setActiveTab(detail.tab as AppTab);
    };
    window.addEventListener('be:navigate', onNavigate);
    return () => window.removeEventListener('be:navigate', onNavigate);
  }, []);

  const saveConversations = (updated: Conversation[]) => {
    conversationsRef.current = updated;
    setConversations(updated);
    localStorage.setItem(CONVERSATIONS_STORAGE_KEY, JSON.stringify(updated));
  };

  // Chat organization (folders / colors / pin / rename / move) is owned by a
  // hook; it mutates the transcript list through this bridge so the conversation
  // store stays here. The base view props are named; the org actions are bundled.
  const chatOrganization = useChatOrganization(
    (update) => saveConversations(update(conversationsRef.current)),
  );
  const loadChatOrganization = chatOrganization.load;
  // Load conversations + folders from local storage
  useEffect(() => {
    if (!mounted) return;
    loadChatOrganization();
    const saved = localStorage.getItem(CONVERSATIONS_STORAGE_KEY);
    if (saved) {
      try {
        // Normalize on load: backfills createdAt + folder/color/pin fields on
        // legacy rows so older transcripts gain organization support cleanly.
        const parsed = normalizeConversations(JSON.parse(saved));
        conversationsRef.current = parsed;
        setConversations(parsed);
        if (parsed.length > 0) {
          activeConversationIdRef.current = parsed[0].id;
          setActiveConversationId(parsed[0].id);
          setMessages(parsed[0].messages);
          void restoreWorkspaceForChat(parsed[0].messages, parsed[0].id);
        } else {
          activeConversationIdRef.current = null;
          setActiveConversationId(null);
          setMessages([]);
          useWorkspaceStore.getState().clear();
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
      useWorkspaceStore.getState().clear();
    }
  }, [mounted, loadChatOrganization]);

  const handleSelectConversation = (id: string) => {
    activeConversationIdRef.current = id;
    setActiveConversationId(id);
    const chat = conversationsRef.current.find(c => c.id === id);
    if (chat) {
      setMessages(chat.messages);
      void restoreWorkspaceForChat(chat.messages, id);
    } else {
      useWorkspaceStore.getState().clear();
    }
  };

  const handleNewChat = () => {
    activeConversationIdRef.current = null;
    setActiveConversationId(null);
    setMessages([]);
    useWorkspaceStore.getState().clear();
  };

  const handleDeleteConversation = (id: string) => {
    const updated = conversationsRef.current.filter(c => c.id !== id);
    saveConversations(updated);
    if (activeConversationIdRef.current === id) {
      if (updated.length > 0) {
        activeConversationIdRef.current = updated[0].id;
        setActiveConversationId(updated[0].id);
        setMessages(updated[0].messages);
        void restoreWorkspaceForChat(updated[0].messages, updated[0].id);
      } else {
        activeConversationIdRef.current = null;
        setActiveConversationId(null);
        setMessages([]);
        useWorkspaceStore.getState().clear();
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
        timestamp: Date.now(),
        createdAt: Date.now()
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
          timestamp: Date.now(),
          createdAt: Date.now()
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
        createdAt: Date.now(),
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
    // Attachments made on the empty state must land in the session folder BEFORE
    // the run starts, or the run's context documents miss them. This awaits the
    // upload, so the first turn sees the attached file.
    try {
      await sessionController.flushPending(chatId);
    } catch {
      // A failed flush must not block the send; the error is surfaced on the bar.
    }
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
        vision: turn.vision,
        memory: turn.memory,
        runId: turn.runId,
        model: turn.model,
        error: turn.error,
        pendingApproval: turn.pendingApproval,
      }, turn.done);    };

    setAgentBusy(true);
    sound.tick();

    try {
      const finalTurn = await agentRun.start({ history, userText, chatId, model: chatModel.displayModel || undefined, reasoningEffort: reasoningEffort.effort });
      setSessionRefreshKey((k) => k + 1);
      // A finished reply is an incoming message, not a generic success.
      if (finalTurn.status === 'completed' && (finalTurn.finalText || finalTurn.text)) sound.message();
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

  /** Run a follow-up turn from a response `controls` block (same path as send). */
  const handleFollowup = (prompt: string) => {
    const text = prompt.trim();
    if (!text || agentBusy) return;
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: text };
    const chatId = addMessageToActiveChat(userMsg);
    void runAgent(chatId, text, userMsg);
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

  // The Market Regime panel dispatches `be:ask-eclipse` with a grounded prompt
  // (built from the live regime read). Route it through the same agent path so
  // the explanation is tool-backed, never a canned reply.
  useEffect(() => {
    const onAsk = (e: Event) => {
      const prompt = (e as CustomEvent<{ prompt?: string }>).detail?.prompt;
      if (!prompt) return;
      setActiveTab('chat');
      const userMsg: Message = { id: Date.now().toString(), role: 'user', content: prompt };
      const chatId = addMessageToActiveChat(userMsg);
      void runAgentPrompt(chatId, prompt);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };
    window.addEventListener('be:ask-eclipse', onAsk);
    return () => window.removeEventListener('be:ask-eclipse', onAsk);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const chatRootRef = useRef<HTMLDivElement>(null);
  const appRootRef = useRef<HTMLDivElement>(null);
  // Hydrate the terminal's persisted state and tuck it away in focus mode.
  useTerminalShell(focusMode);

  // Focus mode is chat-only: leave it the moment another tab is opened, and
  // never keep it on while the settings modal is up.
  useEffect(() => {
    if (focusMode && activeTab !== 'chat') setFocusMode(false);
  }, [focusMode, activeTab]);
  useEffect(() => {
    if (focusMode && settingsOpen) setFocusMode(false);
  }, [focusMode, settingsOpen]);
  // Ctrl+Alt+X toggles focus mode anywhere in the app shell (chat tab only).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!matchesShortcut(event, 'ctrl+alt+x') || !isKeyboardEventAvailable(event)) return;
      if (useKeyboardShortcutsStore.getState().helpOpen || hasBlockingKeyboardDialog()) return;
      if (activeTabRef.current !== 'chat') return;
      event.preventDefault();
      setFocusMode((v) => !v);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
  const handleBack = () => {
    if (settingsOpen || mobileMenuOpen) return;
    const target = backTarget(navHistoryRef.current);
    if (!target) return;
    navHistoryRef.current = target.history;
    setNavHistory(target.history);
    setActiveTab(target.tab);
  };
  usePageShortcuts(chatRootRef, [
    // New ChatBot page. Ctrl/Cmd+N (mod+n) is distinct from the layout/new-item
    // `Shift+N` used by other screens (Command Center layouts, trades, alerts).
    { id: 'chat.new', label: 'New chat', keys: 'mod+n', run: handleNewChat, enabled: activeTab === 'chat' && !settingsOpen && !mobileMenuOpen },
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
    <div ref={appRootRef} className="app-page-bg relative flex flex-col h-[100dvh] w-full bg-background text-foreground font-sans selection:bg-primary/30 overflow-hidden">
      {/* Keyboard users can jump straight past the sidebar to the main content. */}
      <a href="#main-content" className="skip-to-content">
        {t('a11y.skipToContent')}
      </a>
      {/* Aurora full-viewport top glow — reflects blended market + news sentiment */}
      <AuroraGlow />
      {/* Market Regime panel — headless; opened from the global search / shell.
          Not a header control. */}
      <MarketRegimeControl />

      {/* The primary row: sidebar | main column | optional right-docked terminal.
          The terminal is a REAL column here, so the main panel shrinks to make
          room instead of being overlapped. */}
      <div className="flex-1 flex flex-col md:flex-row min-h-0 overflow-hidden">
        <Sidebar 
          activeTab={activeTab} 
          onChangeTab={setActiveTab} 
          conversations={conversations}
          organization={chatOrganization}
          activeConversationId={activeConversationId}
          onSelectConversation={handleSelectConversation}
          onNewChat={handleNewChat}
          onDeleteConversation={handleDeleteConversation}
          onOpenSettings={() => setSettingsOpen(true)}
          mobileOpen={mobileMenuOpen}
          onCloseMobile={() => setMobileMenuOpen(false)}
          hidden={focusMode}
        />

        <div
          className={cn(
            'flex-1 flex flex-col relative z-10 overflow-hidden min-w-0 h-full',
            activeTab !== 'chat' &&
              'glass-card before:pointer-events-none before:absolute before:inset-x-0 before:top-0 before:h-px before:bg-gradient-to-r before:from-transparent before:via-white/60 dark:before:via-white/10 before:to-transparent',
          )}
        >
        {/* ChatBot wallpaper. Sits in the main content panel (right of the
            sidebar) so it resizes with the panel and stays fully visible when
            the sidebar opens/closes. Rendered only on the chat landing (empty
            transcript); the vars come from the background store and paint
            `none` unless an image is set. */}
        {activeTab === 'chat' && messages.length === 0 && (
          <div aria-hidden className="app-bg-layer" />
        )}

        {/* Giant ChatBot wordmark (Settings › General › Background). Painted
            above the wallpaper but below the transcript/composer, landing only. */}
        {activeTab === 'chat' && messages.length === 0 && <ChatWordmark />}

        <TopBar 
          onToggleMenu={() => setMobileMenuOpen(true)}
          activeTab={activeTab}
          hidden={focusMode}
        />

        <div id="main-content" className="flex-1 overflow-y-auto relative w-full h-full z-10" tabIndex={-1}>
          {/* Keep-alive tabs: a tab mounts on first visit (visited set) and
              then stays mounted hidden — revisits are instant with no chunk
              reload, no refetch, no loader flash. Unvisited tabs render
              nothing, preserving the old single-screen boot behavior. */}
          {visited.has('dashboard') && (
            <div data-keepalive-panel className={cn('w-full h-full', activeTab === 'dashboard' ? '' : 'hidden')}>
              <div className="flex-1 w-full px-2 md:px-4 py-3">
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
            <div
              ref={chatRootRef}
              data-keyboard-scope="Chat"
              className={activeTab === 'chat' ? 'w-full h-full' : 'hidden'}
            >
              <div className={cn(
                'w-full h-full flex flex-col items-center justify-between pt-2 md:pt-4 relative min-w-0 transition-[padding] duration-500 ease-out',
                focusMode && 'pt-0',
              )}
                style={{ fontFamily: 'var(--chat-font, var(--font-sans))' }}
              >
                {messages.length === 0 ? (
                  <div className="flex-1 flex w-full flex-col items-center min-h-0">
                    <EmptyState
                      query={query}
                      setQuery={setQuery}
                      onSend={handleSend}
                      onViewMarketOverview={() => setActiveTab('discovery')}
                      onAttach={() => fileInputRef.current?.click()}
                      attachments={attachmentChips}
                      onRemoveAttachment={handleRemoveAttachment}
                      busy={agentBusy}
                      onCancel={handleCancel}
                      focus={focusMode}
                      modelState={chatModel}
                      effortState={reasoningEffort}
                    />
                    <div className="w-full px-4 md:px-6">
                      <SessionBar session={sessionController} />
                    </div>
                  </div>
                ) : (
                  <div className={cn(
                    'flex-1 flex flex-col items-center w-full min-h-0 relative z-10 overflow-hidden justify-between transition-[max-width] duration-500 ease-out',
                    focusMode && 'max-w-[860px] mx-auto',
                  )}>
<ChatHistory
  messages={messages}
  onEditMessage={handleEditMessage}
  onRetryMessage={handleRetryMessage}
  onFeedback={handleFeedback}
  onFollowup={handleFollowup}
/>
                    <div className={cn(
                      'w-full mx-auto px-4 md:px-6 relative group mt-auto shrink-0 pb-1 transition-[max-width] duration-500 ease-out',
                      focusMode ? 'max-w-[860px]' : 'max-w-[1400px]',
                    )} ref={setComposerEl}>
                      <ChatInput
                        query={query}
                        setQuery={setQuery}
                        onSend={handleSend}
                        placeholder="Ask a follow-up..."
                        showProvider={false}
                        modelState={chatModel}
                        effortState={reasoningEffort}
                        busy={agentBusy}
                        onCancel={handleCancel}
                        onAttach={() => fileInputRef.current?.click()}
                        attaching={sessionController.busy}
                        attachments={attachmentChips}
                        onRemoveAttachment={handleRemoveAttachment}
                        contextLabel={sessionController.session && sessionController.session.contextChars > 0
                          ? `${(sessionController.session.contextChars / 1000).toFixed(1)}k / ${(sessionController.session.contextLimitChars / 1000).toFixed(0)}k chars`
                          : undefined}
                        contextFraction={sessionController.session
                          ? sessionController.session.contextChars / sessionController.session.contextLimitChars
                          : 0}
                      />
                      {pendingApproval && (
                        <ApprovalCard
                          approval={pendingApproval}
                          anchor={composerEl}
                          onDecide={agentRun.decide}
                        />
                      )}
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

          {visited.has('artifacts') && (
            <div className={cn('w-full h-full', activeTab === 'artifacts' ? '' : 'hidden')}>
              <div className="flex-1 w-full px-4 md:px-8 py-8 overflow-y-auto">
                <ArtifactsScreen />
              </div>
            </div>
          )}

          {visited.has('tasks') && (
            <div className={cn('w-full h-full', activeTab === 'tasks' ? '' : 'hidden')}>
              <div className="flex-1 w-full px-4 md:px-8 py-8 overflow-y-auto">
                <TasksScreen />
              </div>
            </div>
          )}

          {visited.has('ui-builder') && (
            <div className={cn('w-full h-full', activeTab === 'ui-builder' ? '' : 'hidden')}>
              <div className="flex-1 w-full px-4 md:px-8 py-8 overflow-y-auto">
                <UiBuilderScreen />
              </div>
            </div>
          )}

          {visited.has('pages') && (
            <div className={cn('w-full h-full', activeTab === 'pages' ? '' : 'hidden')}>
              <div className="flex-1 w-full px-4 md:px-8 py-8">
                <PagesScreen />
              </div>
            </div>
          )}

          {visited.has('backtest') && (
            <div className={cn('w-full h-full', activeTab === 'backtest' ? '' : 'hidden')}>
              <div className="flex-1 w-full px-4 md:px-8 py-8 overflow-y-auto">
                <BacktestScreen />
              </div>
            </div>
          )}

          {visited.has('research-data') && (
            <div className={cn('w-full h-full', activeTab === 'research-data' ? '' : 'hidden')}>
              <div className="flex-1 w-full px-4 md:px-8 py-8 overflow-y-auto">
                <ResearchDataScreen />
              </div>
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
                  <ArrowLeft size={13} /> Back to Market Discover
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
        {/* Close the main column, then place the right dock as a SIBLING column
            in the row, so the main panel shrinks instead of being overlapped. */}
        </div>
        <AgentWorkspace />
        <TerminalDock slot="right" />
      </div>

      {/* Bottom-docked terminal: a real strip below the row, above the footer. */}
      <TerminalDock slot="bottom" />
      {/* Full-page terminal: an overlay, since nothing else is visible behind it. */}
      <TerminalDock slot="full" />

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
