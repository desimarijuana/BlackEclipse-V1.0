'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Plus, ArrowUp, Pause, Loader2, FileText, X, Layers, Image as ImageIcon, Blocks, SquarePen, MessageSquareText, Terminal } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { ProviderLogo } from '@/components/providers/provider-logo';
import { VoiceInputButtonView } from './voice-input-button';
import { VoiceFireField } from './voice-fire-field';
import { MentionPalette, type MentionOption } from './mention-palette';
import { ModelSelector } from './model-selector';
import { useVoiceInput } from '@/hooks/use-voice-input';
import { insertTranscript } from '@/lib/voice/insert';
import { cn } from '@/lib/utils';
import { getAgentProvider } from '@/lib/agent/registry';
import { useCommandStore } from '@/lib/search/store';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { ChatModelState } from '@/lib/agent/use-chat-model';
import type { ReasoningEffortState } from '@/lib/agent/use-reasoning-effort';
import { EffortControl } from './effort-control';
import { QuantModeControl } from './quant-mode-control';
import { ChoicesModeControl } from './choices-mode-control';
import { PlanModeControl } from './plan-mode-control';
import { TradeApprovalBanner } from './trade-approval-banner';
import { GoalBar } from './goal-bar';
import { resolveCommand, type CommandSpec } from '@/lib/harness/commands/command-registry';
import { recordCommandRun, useCommandMemory } from '@/lib/harness/commands/command-history';
import { useCommandSuggestions } from '@/lib/harness/commands/command-suggest';
import { useProjectCommands } from '@/lib/harness/use-project-commands';
import { ActiveCommandBadge, CommandPalette, useCommandPalette } from './command-palette';
import { CommandPaletteDialog } from './command-dialog';
import { CommandSuggestions } from './command-suggestions';
import { searchMentions, mentionedTargets, type MentionTarget } from '@/lib/bots/mentions';
import { isLongPaste } from '@/lib/chat/paste';
import { originLabel, describeSource, type FileRef } from '@/lib/chat/file-sources';
import type { FileOrigin } from '@/lib/chat/session-types';
import { BotAvatar } from '@/components/bots/bot-avatar';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { avatarFor, useBotAvatarStore, useHydrateBotAvatars } from '@/lib/bots/avatar-store';
import { ghostSpecFromId } from '@/lib/bots/ghost';
import { useT } from '@/lib/i18n/use-t';
import { isKeyboardScopeVisible } from '@/lib/keyboard';
import { CHAT_FOCUS_EVENT } from '@/hooks/use-chat-focus-keybind';
import type { QueuedPrompt } from '@/lib/chat/message-queue';
import type { MessageQuote } from '@/types/chat';
import { quoteSourceLabel } from '@/lib/chat/quote';
import { MessageQueue } from './message-queue';
import { isShellDraft, shellCommandOf, SHELL_PLACEHOLDER } from '@/lib/chat/shell';

// Grow the composer to roughly four lines, then scroll instead of growing.
const MAX_HEIGHT = 120;
// Cap the `@` palette the same way.
const MAX_MENTION_RESULTS = 8;

/** The trailing `@token` the user is typing (null = no open mention token). */
function mentionTokenOf(text: string): string | null {
  // Path separators are allowed so `@src/components` can search project files.
  const m = /(?:^|\s)@([\w.\-/]*)$/.exec(text);
  return m ? m[1] : null;
}

/** One attached file shown as a chip above the composer. */
export interface AttachmentChip {
  name: string;
  /** True while the upload is still in flight (for a pending attachment). */
  uploading?: boolean;
  /** Where the file is from — shown so a chip is never an anonymous name. */
  origin?: FileOrigin;
  sourcePath?: string | null;
  rootLabel?: string | null;
}

interface ChatInputProps {
  query: string;
  setQuery: (val: string) => void;
  onSend: (e: React.FormEvent) => void;
  /**
   * Run a `!` shell command instead of sending a prompt. When provided, a draft
   * that starts with `!` becomes shell mode (OpenCode parity): Enter runs it in
   * the session workspace, Esc leaves the mode, and the run is appended to the
   * transcript rather than sent to the agent. Omitted → `!` is ordinary text.
   */
  onRunShell?: (command: string) => void | Promise<void>;
  placeholder?: string;
  autoFocus?: boolean;
  /** Show the real configured provider label as a quiet pill. */
  showProvider?: boolean;
  /**
   * The composer's model selector state (real, never a fabricated list). When
   * provided, the pill becomes a dropdown that switches the model for the next
   * turn; when omitted only the provider label is shown.
   */
  modelState?: ChatModelState;
  /**
   * The composer's per-question reasoning-effort ("model intelligence") state.
   * When provided, an effort pill renders beside the model selector; the chosen
   * level is sent with the next run only (Auto sends no override).
   */
  effortState?: ReasoningEffortState;
  /** The assistant is working: submit becomes a pause (cancel) button. */
  busy?: boolean;
  /** Called when the user clicks pause. */
  onCancel?: () => void;
  /** Opens the file picker — the "+" is the attach-documents affordance. */
  onAttach?: () => void;
  /**
   * Open an image/photo picker. When absent, "Images and photos" falls back to
   * the document picker so the action is never a dead end.
   */
  onAttachImage?: () => void;
  /** Shows a spinner on the "+" while documents upload. */
  attaching?: boolean;
  /**
   * Attached documents rendered as visible chips above the composer, so an
   * attachment is obviously present without expanding anything. Removing a chip
   * calls `onRemoveAttachment` with its name.
   */
  attachments?: AttachmentChip[];
  onRemoveAttachment?: (name: string) => void;
  /** A selected passage waiting to be sent with the next turn. */
  quote?: MessageQuote | null;
  onClearQuote?: () => void;
  /** Open an attachment so its content can be READ before sending. */
  onOpenAttachment?: (name: string) => void;
  /**
   * A short "context used" label (e.g. `4.2k / 60k`). Rendered quietly under
   * the composer; omitted when there is nothing to report.
   */
  contextLabel?: string;
  /** 0–1 fraction for the small usage meter. */
  contextFraction?: number;
  /**
   * Bots and group chats the user can `@`-mention from this composer. When
   * provided, typing `@` opens a palette and the message routes to the mentioned
   * bot(s)/room(s) on send. Omitted on composers that have no bots to reach.
   */
  mentionTargets?: MentionTarget[];
  /**
   * Async project-file search for the `@` palette. Results appear in a "Files"
   * section beside the bots/rooms, each showing its folder path. When omitted
   * only mentions are searchable.
   */
  searchProjectFiles?: (query: string) => Promise<FileRef[]>;
  /** Called when a project file is chosen from the `@` palette. */
  onReferenceFile?: (ref: FileRef) => void;
  /**
   * Handle a PASTE too big to belong in the composer: the caller attaches it as
   * a document (and it shows as a chip, the way an uploaded file does). When
   * absent, a long paste is inserted normally.
   */
  onPasteText?: (text: string) => void;
  /**
   * Prompts waiting to run after the current reply. While the agent is busy a
   * submit QUEUES the draft instead of dropping it; the panel lets the user
   * edit, reorder, remove or promote each item.
   */
  queued?: QueuedPrompt[];
  onQueueEdit?: (id: string, text: string) => void;
  onQueueRemove?: (id: string) => void;
  onQueueMove?: (id: string, direction: 'up' | 'down') => void;
  onQueueRunNow?: (id: string) => void;
  onQueueClear?: () => void;
}

export function ChatInput({ 
  query, 
  setQuery, 
  onSend, 
  onRunShell,
  placeholder = "Ask about a stock, sector, or market trend...", 
  autoFocus,
  showProvider = true,
  modelState,
  effortState,
  busy = false,
  onCancel,
  onAttach,
  onAttachImage,
  attaching = false,
  attachments,
  onRemoveAttachment,
  quote,
  onClearQuote,
  onOpenAttachment,
  contextLabel,
  contextFraction,
  mentionTargets,
  searchProjectFiles,
  onReferenceFile,
  onPasteText,
  queued,
  onQueueEdit,
  onQueueRemove,
  onQueueMove,
  onQueueRunNow,
  onQueueClear,
  }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Dictation inserts at the caret captured when the mic is pressed, never at
  // the end: a spoken sentence must be able to complete something already typed.
  const queryRef = useRef(query);
  queryRef.current = query;
  const voiceSelectionRef = useRef<{ start: number; end: number } | null>(null);
  const captureVoiceSelection = useCallback(() => {
    const el = textareaRef.current;
    voiceSelectionRef.current = el
      ? { start: el.selectionStart, end: el.selectionEnd }
      : null;
  }, []);
  const insertVoiceText = useCallback(
    (text: string) => {
      const { value, caret } = insertTranscript(
        queryRef.current,
        text,
        voiceSelectionRef.current ?? undefined,
      );
      setQuery(value);
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.focus();
        try {
          el.setSelectionRange(caret, caret);
        } catch {
          /* selection unavailable */
        }
      });
    },
    [setQuery],
  );
  // The composer owns the dictation session so it can morph into the voice
  // field on the same state. Insertion still goes through `insertVoiceText`.
  const voice = useVoiceInput(insertVoiceText);
  const voiceActive = voice.state !== 'idle';
  const cancelVoiceRef = useRef(voice.cancel);
  cancelVoiceRef.current = voice.cancel;
  // Escape must cancel even when the pointer has moved focus out of the hidden
  // textarea (clicking the flame field blurs it).
  useEffect(() => {
    if (!voiceActive) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      cancelVoiceRef.current();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [voiceActive]);
  // The REAL configured provider, never a fabricated model list.
  const providerLabel = useMemo(() => getAgentProvider().label, []);
  // Translated copy for the command palette / badge (i18n keys, not literals).
  const t = useT();

  // Auto-grow the composer with its content up to a cap, then scroll. A long
  // prompt no longer stays clipped on one line.
  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    // An EMPTY composer stays exactly one line. The placeholder is allowed to
    // wrap, which inflates `scrollHeight` — on a narrow (mobile) width that
    // would grow the bar into a 3-line block for no reason. Only real typed
    // content grows it; clearing the inline height falls back to `rows={1}`.
    if (el.value.length === 0) {
      el.style.height = '';
      el.style.overflowY = 'hidden';
      return;
    }
    el.style.height = 'auto';
    const needed = el.scrollHeight;
    el.style.height = `${Math.min(needed, MAX_HEIGHT)}px`;
    // Only show a scrollbar once the content truly exceeds the cap; otherwise a
    // 1px rounding gap would render a full-height thumb next to the buttons.
    el.style.overflowY = needed > MAX_HEIGHT ? 'auto' : 'hidden';
  }, []);

  useEffect(() => { resize(); }, [query, resize]);

  // `/` (broadcast globally) places the caret here. Only the composer actually
  // on screen answers — a keep-alive tab hidden with `display:none` fails the
  // visibility test, so the ChatDock (or the other composer) gets the focus.
  useEffect(() => {
    const onFocusChat = () => {
      const el = textareaRef.current;
      if (el && isKeyboardScopeVisible(el)) el.focus();
    };
    window.addEventListener(CHAT_FOCUS_EVENT, onFocusChat);
    return () => window.removeEventListener(CHAT_FOCUS_EVENT, onFocusChat);
  }, []);

  // ── Slash-command palette ──────────────────────────────────────────────
  // Typing a bare `/word` (no space yet) opens the shared command palette.
  // Selecting one inserts `/name ` and focuses the composer. The palette owns
  // grouping, recents/pins and the detail pane; ⌘K opens the full dialog.
  const {
    token: commandToken,
    sections: commandSections,
    flat: commandMatches,
    open: commandMenuOpen,
    highlight: commandHighlight,
    setHighlight: setCommandHighlight,
    listRef: commandListRef,
  } = useCommandPalette(query);
  const { favorites: commandFavorites } = useCommandMemory();
  const projectCommands = useProjectCommands();
  const [commandDialogOpen, setCommandDialogOpen] = useState(false);
  const suggestions = useCommandSuggestions(query, true);
  const suggestionListRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = suggestionListRef.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    el?.scrollIntoView({ block: 'nearest' });
  }, [suggestions.highlight, suggestions.visible]);
  const applySuggestion = useCallback(
    (value: string) => {
      const next = suggestions.apply(value);
      if (next === null) return;
      setQuery(`${next} `);
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    [suggestions, setQuery],
  );

  const completeCommand = useCallback(
    (c: CommandSpec) => {
      setQuery(`/${c.name} `);
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    [setQuery],
  );

  // A recognized command already followed by an instruction: show a badge.
  const activeCommand = useMemo<CommandSpec | null>(() => {
    const m = /^\s*\/([A-Za-z][A-Za-z0-9_-]*)\s/.exec(query);
    return m ? (resolveCommand(m[1], projectCommands) ?? null) : null;
  }, [query, projectCommands]);

  // ⌘K / Ctrl+K opens the full command dialog. Only the visible composer answers
  // so a keep-alive tab cannot open a second palette.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== 'k') return;
      const el = textareaRef.current;
      if (!el || !isKeyboardScopeVisible(el)) return;
      e.preventDefault();
      setCommandDialogOpen(true);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // ── `!` shell mode ──────────────────────────────────────────────────────────
  // Derived from the draft, not a hidden toggle: `!` at the start runs the line
  // through the session workspace shell (OpenCode parity). Deleting the `!`
  // leaves the mode, so the composer can never be silently stuck in it.
  const shellMode = !!onRunShell && isShellDraft(query);

  // Remember the command (not the prose) when a draft is submitted. Consecutive
  // duplicates are de-duplicated by the store, so the form/keydown double path
  // is harmless.
  const recordDraftCommand = useCallback(() => {
    const m = /^\s*\/([A-Za-z][A-Za-z0-9_-]*)/.exec(queryRef.current);
    if (m) recordCommandRun(m[1]);
  }, []);
  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      // Shell mode owns submit: a `!` draft RUNS, it is never sent as a prompt.
      if (shellMode && onRunShell) {
        e.preventDefault();
        const command = shellCommandOf(queryRef.current);
        if (!command) return;
        setQuery('');
        void onRunShell(command);
        return;
      }
      recordDraftCommand();
      onSend(e);
    },
    [onSend, onRunShell, recordDraftCommand, shellMode, setQuery],
  );

  // ── Bot / group / file `@mention` palette ────────────────────────────────
  // Typing `@word` (start of text or after a space, no space yet) opens a menu of
  // the user's bots and group chats, plus matching project files. Selecting a
  // bot inserts `@Name `; selecting a file inserts its relative path and asks
  // the host to attach it as context. Inert without `mentionTargets`.
  useHydrateBotAvatars();
  const mentionAvatars = useBotAvatarStore((s) => s.avatars);
  const [mentionHighlight, setMentionHighlight] = useState(0);
  const mentionToken = useMemo(() => mentionTokenOf(query), [query]);
  const mentionMatches = useMemo<MentionTarget[]>(() => {
    if (mentionToken === null || !mentionTargets || mentionTargets.length === 0) return [];
    return searchMentions(mentionTargets, mentionToken, MAX_MENTION_RESULTS);
  }, [mentionToken, mentionTargets]);

  // Project-file results are async and debounced so a fast typist does not fire
  // one runtime walk per keystroke. A stale response is dropped by the `alive`
  // flag; a runtime error simply yields no file section.
  const [fileMatches, setFileMatches] = useState<FileRef[]>([]);
  const [fileSearching, setFileSearching] = useState(false);
  useEffect(() => {
    if (mentionToken === null || !searchProjectFiles) {
      setFileMatches([]);
      setFileSearching(false);
      return;
    }
    let alive = true;
    setFileSearching(true);
    const timer = setTimeout(() => {
      searchProjectFiles(mentionToken)
        .then((hits) => { if (alive) setFileMatches(hits); })
        .catch(() => { if (alive) setFileMatches([]); })
        .finally(() => { if (alive) setFileSearching(false); });
    }, 120);
    return () => { alive = false; clearTimeout(timer); };
  }, [mentionToken, searchProjectFiles]);

  const mentionOptions = useMemo<MentionOption[]>(() => [
    ...mentionMatches.map((target) => ({ kind: 'bot' as const, target })),
    ...fileMatches.map((file) => ({ kind: 'file' as const, file })),
  ], [mentionMatches, fileMatches]);
  const mentionMenuOpen = mentionToken !== null && mentionOptions.length > 0;
  useEffect(() => { setMentionHighlight(0); }, [mentionToken]);

  const mentionListRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = mentionListRef.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    el?.scrollIntoView({ block: 'nearest' });
  }, [mentionHighlight, mentionMenuOpen]);

  const completeMention = useCallback(
    (option: MentionOption | undefined) => {
      if (!option) return;
      // Replace only the partial token being typed; never clobber earlier text.
      if (option.kind === 'bot') {
        setQuery(query.replace(/@([\w.\-/]*)$/, `@${option.target.name} `));
      } else {
        const path = option.file.path;
        setQuery(query.replace(/@([\w.\-/]*)$/, `@${path} `));
        onReferenceFile?.(option.file);
      }
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    [setQuery, query, onReferenceFile],
  );

  // Resolved mentions already in the draft: chips so the user sees exactly which
  // bots/rooms the message will reach before sending.
  const activeMentions = useMemo(
    () => (mentionTargets ? mentionedTargets(query, mentionTargets) : []),
    [query, mentionTargets],
  );

  // A big paste is a DOCUMENT, not a message: hand it to the caller to attach
  // (it shows as a chip) instead of dumping thousands of lines into the
  // composer. Small pastes, and every paste where no handler is wired, behave
  // normally.
  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!onPasteText) return;
    const text = e.clipboardData.getData('text');
    if (!isLongPaste(text)) return;
    e.preventDefault();
    onPasteText(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Dictation owns the keyboard while it is open: Esc cancels, Enter stops and
    // transcribes. Never send an empty prompt mid-dictation.
    if (voiceActive) {
      if (e.key === 'Escape') {
        e.preventDefault();
        voice.cancel();
        return;
      }
      if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault();
        voice.stop();
        return;
      }
    }
    // Shell mode: Esc leaves the mode without running anything (OpenCode parity).
    // Only when no palette is open — palettes own Escape while they are visible.
    if (
      shellMode &&
      e.key === 'Escape' &&
      !mentionMenuOpen &&
      !commandMenuOpen &&
      !suggestions.visible
    ) {
      e.preventDefault();
      setQuery('');
      return;
    }
    // The `@` palette takes priority: arrows navigate it and Enter/Tab completes
    // the highlighted mention (instead of sending).
    if (mentionMenuOpen && !e.nativeEvent.isComposing) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setMentionHighlight((h) => (h + 1) % mentionOptions.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setMentionHighlight((h) => (h - 1 + mentionOptions.length) % mentionOptions.length);
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        completeMention(mentionOptions[Math.min(mentionHighlight, mentionOptions.length - 1)]);
        return;
      }
    }
    // Argument suggestions (skills, symbols, …) take priority over sending: the
    // user is completing an argument, not finishing the command.
    if (suggestions.visible && !e.nativeEvent.isComposing) {
      const count = suggestions.candidates.length;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        suggestions.setHighlight((suggestions.highlight + 1) % count);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        suggestions.setHighlight((suggestions.highlight - 1 + count) % count);
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        const candidate = suggestions.candidates[Math.min(suggestions.highlight, count - 1)];
        if (candidate) applySuggestion(candidate.value);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        suggestions.dismiss();
        return;
      }
    }
    // While the command menu is open, the arrows navigate it and Enter/Tab
    // completes the highlighted command (instead of sending).
    if (commandMenuOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setCommandHighlight((h) => (h + 1) % commandMatches.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setCommandHighlight((h) => (h - 1 + commandMatches.length) % commandMatches.length);
        return;
      }
      if ((e.key === 'Enter' || e.key === 'Tab') && !e.nativeEvent.isComposing) {
        e.preventDefault();
        completeCommand(commandMatches[commandHighlight]);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setQuery('');
        return;
      }
    }
    // Enter sends; Shift+Enter inserts a newline. Ignore IME composition.
    // While the agent is busy the host QUEUES the prompt instead of dropping it,
    // so submit is always forwarded and the host decides send-vs-queue.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (shellMode && onRunShell) {
        const command = shellCommandOf(queryRef.current);
        if (command) {
          setQuery('');
          void onRunShell(command);
        }
        return;
      }
      recordDraftCommand();
      onSend(e);
    }
  };

  const filled = Math.max(0, Math.min(1, contextFraction ?? 0));

  // The `/` palette is PORTALED to <body> so its backdrop blur samples the real
  // page instead of a scoped backdrop root (the app shell's glass surfaces),
  // which would silently flatten the frost. Its box is tracked to the composer.
  const formRef = useRef<HTMLFormElement>(null);
  const [paletteBox, setPaletteBox] = useState<{ left: number; width: number; bottom: number } | null>(null);
  useLayoutEffect(() => {
    if (!commandMenuOpen && !mentionMenuOpen && !suggestions.visible) {
      setPaletteBox(null);
      return;
    }
    const el = formRef.current;
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      setPaletteBox({ left: r.left, width: r.width, bottom: window.innerHeight - r.top + 8 });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [commandMenuOpen, mentionMenuOpen, suggestions.visible]);

  // Insert a token (e.g. `/` or `@`) at the end of the draft and keep focus in
  // the composer so the corresponding palette opens immediately.
  const insertToken = useCallback((token: string) => {
    const base = query.replace(/\s+$/, '');
    setQuery(base ? `${base} ${token}` : token);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.focus();
      const end = el.value.length;
      try {
        el.setSelectionRange(end, end);
      } catch {
        /* setSelectionRange is unavailable on some input types */
      }
    });
  }, [query, setQuery]);

  const openCanvas = useCallback(() => {
    useCommandStore.getState().openCanvas();
    useCommandStore.getState().dispatch({ tab: 'chat' });
  }, []);

  // The `/` palette only opens when the draft begins with `/`, so Skills seeds
  // an empty composer with `/`; a non-empty draft gets the token appended.
  const openSkillsPalette = useCallback(() => {
    if (!query.trim()) setQuery('/');
    else insertToken('/');
  }, [query, setQuery, insertToken]);

  return (
    <div className="w-full">
      <GoalBar />
      <TradeApprovalBanner onCancel={onCancel} />
      {queued && queued.length > 0 && onQueueEdit && onQueueRemove && onQueueMove && onQueueRunNow && onQueueClear && (
        <MessageQueue
          items={queued}
          busy={busy}
          onEdit={onQueueEdit}
          onRemove={onQueueRemove}
          onMove={onQueueMove}
          onRunNow={onQueueRunNow}
          onClear={onQueueClear}
        />
      )}
      {quote && (
        <div className="mb-2 flex items-start gap-2 rounded-2xl border border-primary/30 bg-primary/10 px-2.5 py-2 text-[11px]">
          <MessageSquareText size={13} className="mt-0.5 shrink-0 text-primary" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-primary">Quoted · {quoteSourceLabel(quote)}</span>
              {quote.truncated && <span className="text-[10px] text-muted-foreground/70">shortened</span>}
            </div>
            <p className="mt-0.5 max-h-16 overflow-hidden whitespace-pre-wrap break-words text-foreground/80">
              {quote.text}
            </p>
          </div>
          {onClearQuote && (
            <button
              type="button"
              onClick={onClearQuote}
              title="Remove quoted passage"
              aria-label="Remove quoted passage"
              className="shrink-0 rounded-full p-0.5 text-muted-foreground/70 hover:bg-white/10 hover:text-foreground cursor-pointer"
            >
              <X size={11} />
            </button>
          )}
        </div>
      )}
      {attachments && attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5" aria-label="Attached documents">
          {attachments.map((file) => {
            const source = describeSource({
              origin: file.origin ?? 'upload',
              sourcePath: file.sourcePath ?? null,
              rootLabel: file.rootLabel ?? null,
            });
            return (
              <span
                key={file.name}
                className="group inline-flex max-w-[78vw] sm:max-w-[300px] flex-col gap-0 rounded-xl border border-primary/30 bg-primary/10 px-2 py-1 text-[11px] text-foreground/90"
                title={`${file.name} — ${source}`}
              >
                <span className="flex min-w-0 items-center gap-1.5">
                  {file.uploading ? (
                    <Loader2 size={12} className="shrink-0 animate-spin text-primary" />
                  ) : (
                    <FileText size={12} className="shrink-0 text-primary" />
                  )}
                  {onOpenAttachment ? (
                    <button
                      type="button"
                      onClick={() => onOpenAttachment(file.name)}
                      title={`Open ${file.name}`}
                      className="min-w-0 flex-1 truncate text-left hover:underline"
                    >
                      {file.name}
                    </button>
                  ) : (
                    <span className="min-w-0 flex-1 truncate">{file.name}</span>
                  )}
                  <span className="shrink-0 rounded-full bg-accent/40 px-1.5 py-0.5 text-[8.5px] font-medium uppercase tracking-wide text-muted-foreground/70">
                    {originLabel(file.origin)}
                  </span>
                  {onRemoveAttachment && (
                    <button
                      type="button"
                      onClick={() => onRemoveAttachment(file.name)}
                      title="Remove attachment"
                      aria-label={`Remove ${file.name}`}
                      className="shrink-0 rounded-full p-0.5 text-muted-foreground/70 hover:bg-white/10 hover:text-foreground"
                    >
                      <X size={11} />
                    </button>
                  )}
                </span>
                <span
                  className="min-w-0 truncate pl-[18px] font-mono text-[9.5px] text-muted-foreground/60"
                  title={file.sourcePath ?? source}
                >
                  {file.sourcePath ?? source}
                </span>
              </span>
            );
          })}
        </div>
      )}
      {activeCommand && <ActiveCommandBadge spec={activeCommand} />}
      {activeMentions.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5" aria-label="Mentioned bots and group chats">
          {activeMentions.map((m) => (
            <span
              key={`${m.kind}:${m.id}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 py-0.5 pl-1 pr-2 text-[11px] font-medium text-primary"
              title={m.kind === 'group' ? `Group chat · ${m.description}` : m.description || m.name}
            >
              {m.kind === 'group'
                ? <GhostAvatar spec={ghostSpecFromId(m.id)} size={16} title={m.name} />
                : <BotAvatar botId={m.id} spec={avatarFor(mentionAvatars, m.id)} size={16} title={m.name} />}
              @{m.name}
              <span className="ml-0.5 rounded-full bg-accent/40 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground/70">
                {m.kind}
              </span>
            </span>
          ))}
        </div>
      )}
      <CommandPalette
        anchor={paletteBox}
        open={commandMenuOpen}
        query={commandToken ?? ''}
        sections={commandSections}
        flat={commandMatches}
        highlight={commandHighlight}
        favorites={commandFavorites}
        onHighlight={setCommandHighlight}
        onSelect={completeCommand}
        listRef={commandListRef}
      />
      <CommandSuggestions
        anchor={paletteBox}
        open={suggestions.visible}
        context={suggestions.context}
        candidates={suggestions.candidates}
        loading={suggestions.loading}
        highlight={suggestions.highlight}
        onHighlight={suggestions.setHighlight}
        onSelect={applySuggestion}
        listRef={suggestionListRef}
      />
      <CommandPaletteDialog
        open={commandDialogOpen}
        onOpenChange={setCommandDialogOpen}
        onSelect={completeCommand}
      />
      {mentionMenuOpen && paletteBox && typeof document !== 'undefined' && (
        <MentionPalette
          open
          box={paletteBox}
          label={t('bots.mentions.paletteLabel')}
          options={mentionOptions}
          highlight={mentionHighlight}
          onHighlight={setMentionHighlight}
          onSelect={completeMention}
          searching={fileSearching}
          listRef={mentionListRef}
          avatars={mentionAvatars}
        />
      )}
      <form ref={formRef} onSubmit={handleSubmit} aria-busy={busy} data-voice={voiceActive ? 'active' : undefined} data-shell={shellMode ? 'active' : undefined} className={cn('relative flex flex-col w-full glass-composer border rounded-3xl px-1.5 sm:px-3 py-1.5 shadow-lg shadow-black/20 transition-colors overflow-visible', shellMode ? 'border-primary/45' : 'border-white/10 dark:border-white/5 focus-within:border-primary')}>
        <div className={cn('relative', voiceActive && 'h-[84px]')}>
          {shellMode && (
            <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0 px-2 pt-1.5 font-mono text-[9.5px] uppercase tracking-wide text-primary/80">
              <Terminal size={11} />
              <span>Shell</span>
              <span className="normal-case tracking-normal text-muted-foreground/60">
                runs in the session workspace
              </span>
              <span className="ml-auto normal-case tracking-normal text-muted-foreground/45">
                esc to leave
              </span>
            </div>
          )}
          <textarea 
            ref={textareaRef}
            rows={1}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={shellMode ? SHELL_PLACEHOLDER : placeholder}
            autoFocus={autoFocus}
            readOnly={voiceActive}
            aria-label="Message Eclipse"
            // Keep the placeholder on ONE line while the composer is empty so it
            // clips cleanly instead of wrapping into a tall block on mobile.
            // Typed content returns to normal soft-wrapping (and auto-grow).
            wrap={query.length === 0 ? 'off' : 'soft'}
            className={cn(
              'chat-composer-scroll w-full bg-transparent border-0 outline-none resize-none overflow-x-hidden overflow-y-hidden placeholder:text-muted-foreground text-foreground px-2 sm:px-2.5 pt-2 pb-1 text-sm leading-relaxed min-w-0 focus:outline-none focus:ring-0',
              voiceActive && 'pointer-events-none select-none opacity-0',
            )}
          />
          {voiceActive && (
            <div className="absolute inset-0 z-10">
              <VoiceFireField
                meterRef={voice.meterRef}
                phase={
                  voice.state === 'starting'
                    ? 'starting'
                    : voice.state === 'transcribing'
                      ? 'transcribing'
                      : 'recording'
                }
                transcript={query}
                interim={voice.interim}
                height={84}
                className="h-full"
              />
            </div>
          )}
        </div>
        
        <div className="flex min-w-0 items-end justify-between gap-2 px-0.5">
          {voiceActive && (
            <span className="flex h-8 min-w-0 flex-1 items-center gap-2 overflow-hidden px-1.5 font-mono text-[10px] uppercase tracking-wide text-rose-300/90">
              <span aria-hidden className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-rose-400" />
              <span className="truncate">
                {voice.engine === 'browser'
                  ? 'Browser dictation'
                  : voice.config?.provider === 'local'
                    ? 'On-device dictation'
                    : 'Whisper dictation'}
              </span>
              <span className="hidden shrink-0 normal-case tracking-normal text-muted-foreground/70 md:inline">
                ■ stop to transcribe · esc cancels
              </span>
            </span>
          )}
          {!voiceActive && (
          <DropdownMenu>
            <DropdownMenuTrigger
              type="button"
              disabled={attaching}
              title="Add context, media or a tool"
              aria-label="Add context, media or a tool"
              className="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-0 focus-visible:outline-none disabled:cursor-default disabled:opacity-50"
            >
              {attaching ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" side="top" className="w-56 glass-command-popover">
              <DropdownMenuItem onClick={() => (onAttachImage ?? onAttach)?.()}>
                <ImageIcon size={15} className="shrink-0" />
                <span>Images and photos</span>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onAttach?.()}>
                <Layers size={15} className="shrink-0" />
                <span>Context</span>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={openCanvas}>
                <SquarePen size={15} className="shrink-0" />
                <span>Canvas</span>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={openSkillsPalette}>
                <Blocks size={15} className="shrink-0" />
                <span>Skills</span>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => insertToken('@')}>
                <span aria-hidden className="flex h-[15px] w-[15px] shrink-0 items-center justify-center font-mono text-sm">@</span>
                <span>Mention</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {/* Per-turn preferences. Auto is the default and sends nothing;
                  picking On makes the choice stick for every later run. */}
              <QuantModeControl disabled={busy} />
              <ChoicesModeControl disabled={busy} />
              <PlanModeControl disabled={busy} />
            </DropdownMenuContent>
          </DropdownMenu>
          )}
          <div className="flex min-w-0 shrink-0 items-center justify-end gap-1 sm:gap-2">
            {!voiceActive && (
              <>
                {modelState ? (
                  <ModelSelector state={modelState} />
                ) : showProvider ? (
                  /* The real configured provider — not a fabricated model picker. */
                  <span
                    className="hidden min-[400px]:inline-flex items-center gap-1.5 px-3 py-1 h-7 rounded-full bg-accent/25 border border-border/25 text-muted-foreground text-xs font-medium whitespace-nowrap"
                    title={`Chat provider: ${providerLabel}`}
                  >
                    <ProviderLogo provider={providerLabel} size={12} className="text-primary" />
                    {providerLabel}
                  </span>
                ) : null}
                {effortState && (
                  <EffortControl
                    value={effortState.effort}
                    index={effortState.index}
                    onIndexChange={effortState.setIndex}
                    disabled={busy}
                  />
                )}
              </>
            )}
            <VoiceInputButtonView
              voice={voice}
              onStart={captureVoiceSelection}
              className="h-8 w-8"
            />
            {!voiceActive && (busy ? (
              <div className="flex items-center gap-1.5">
                {(query.trim() || quote || (attachments && attachments.length > 0)) && (
                  <Button
                    type="submit"
                    size="icon"
                    title="Queue this prompt — it runs after the current reply"
                    aria-label="Queue this prompt"
                    className="flex h-8 items-center gap-1 rounded-full border-0 bg-primary px-2.5 text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:ring-0 focus-visible:outline-none"
                  >
                    <ArrowUp size={14} />
                    <span className="hidden text-[11px] font-semibold min-[420px]:inline">Queue</span>
                  </Button>
                )}
                <Button
                  type="button"
                  size="icon"
                  onClick={onCancel}
                  title="Stop generating"
                  aria-label="Stop generating"
                  className="p-1.5 border-0 bg-foreground text-background hover:bg-foreground/90 rounded-full shrink-0 h-8 w-8 cursor-pointer transition-colors flex items-center justify-center focus-visible:ring-0 focus-visible:outline-none"
                >
                  <Pause size={15} fill="currentColor" />
                </Button>
              </div>
            ) : (
              <Button 
                type="submit" 
                size="icon" 
                disabled={!query.trim() && !quote && !(attachments && attachments.length > 0)}
                className="p-1.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-full shrink-0 h-8 w-8 cursor-pointer disabled:opacity-40 disabled:hover:bg-primary transition-opacity flex items-center justify-center focus-visible:ring-0 focus-visible:outline-none"
              >
                <ArrowUp size={17} />
              </Button>
            ))}
          </div>
        </div>
      </form>

      {contextLabel && (
        <div className="mt-1.5 flex items-center justify-center gap-2 text-[11px] text-muted-foreground/70">
          <span className="tabular-nums">Context {contextLabel}</span>
          <span className="h-1 w-16 overflow-hidden rounded-full bg-accent/50">
            <span
              className={cn(
                'block h-full rounded-full transition-all',
                filled >= 0.9 ? 'bg-amber-400/80' : 'bg-primary/60',
              )}
              style={{ width: `${Math.max(2, filled * 100)}%` }}
            />
          </span>
        </div>
      )}
    </div>
  );
}

export { ModelSelector } from './model-selector';
