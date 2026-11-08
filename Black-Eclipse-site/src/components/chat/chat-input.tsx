'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Plus, ArrowUp, Pause, Loader2, Command, FileText, X, ChevronDown, Check, Cpu, KeyRound, Layers, Bot, Users, Image as ImageIcon, Blocks, SquarePen } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { ProviderLogo } from '@/components/providers/provider-logo';
import { VoiceInputButton } from './voice-input-button';
import { insertTranscript } from '@/lib/voice/insert';
import { cn } from '@/lib/utils';
import { getAgentProvider } from '@/lib/agent/registry';
import { useCommandStore } from '@/lib/search/store';
import { useHydrateEnabledModels, compactModels, useEnabledModelsStore } from '@/lib/agent/enabled-models';
import { ManageModelsDialog } from '@/components/screens/manage-models-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
  DropdownMenuGroup,
} from '@/components/ui/dropdown-menu';
import type { ChatModelState } from '@/lib/agent/use-chat-model';
import type { ReasoningEffortState } from '@/lib/agent/use-reasoning-effort';
import { EffortControl } from './effort-control';
import { QuantModeControl } from './quant-mode-control';
import { ChoicesModeControl } from './choices-mode-control';
import { PlanModeControl } from './plan-mode-control';
import { TradeApprovalBanner } from './trade-approval-banner';
import {
  commandArgHint,
  isCommandAvailable,
  searchCommands,
  type CommandSpec,
} from '@/lib/harness/command-registry';
import { searchMentions, mentionedTargets, type MentionTarget } from '@/lib/bots/mentions';
import { isLongPaste } from '@/lib/chat/paste';
import { BotAvatar } from '@/components/bots/bot-avatar';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { avatarFor, useBotAvatarStore, useHydrateBotAvatars } from '@/lib/bots/avatar-store';
import { ghostSpecFromId } from '@/lib/bots/ghost';
import { useT } from '@/lib/i18n/use-t';
import { isKeyboardScopeVisible } from '@/lib/keyboard';
import { CHAT_FOCUS_EVENT } from '@/hooks/use-chat-focus-keybind';

// Grow the composer to roughly four lines, then scroll instead of growing.
const MAX_HEIGHT = 120;
// Cap the `@` palette the same way.
const MAX_MENTION_RESULTS = 8;

/** The trailing `@token` the user is typing (null = no open mention token). */
function mentionTokenOf(text: string): string | null {
  const m = /(?:^|\s)@([\w.-]*)$/.exec(text);
  return m ? m[1] : null;
}

/** One attached file shown as a chip above the composer. */
export interface AttachmentChip {
  name: string;
  /** True while the upload is still in flight (for a pending attachment). */
  uploading?: boolean;
}

interface ChatInputProps {
  query: string;
  setQuery: (val: string) => void;
  onSend: (e: React.FormEvent) => void;
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
   * Handle a PASTE too big to belong in the composer: the caller attaches it as
   * a document (and it shows as a chip, the way an uploaded file does). When
   * absent, a long paste is inserted normally.
   */
  onPasteText?: (text: string) => void;
}

export function ChatInput({ 
  query, 
  setQuery, 
  onSend, 
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
  onOpenAttachment,
  contextLabel,
  contextFraction,
  mentionTargets,
  onPasteText,
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
  // Typing a bare `/word` (no space yet) opens a small menu of matching chat
  // commands. Selecting one inserts `/name ` and focuses the composer so the
  // user types the instruction. Distinct from the global `/` shortcut, which
  // focuses this composer (and only fires while it is NOT focused).
  const [commandHighlight, setCommandHighlight] = useState(0);
  const commandToken = useMemo(() => {
    const t = query.trimStart();
    if (!t.startsWith('/')) return null;
    const body = t.slice(1);
    if (/\s/.test(body)) return null; // past the command word: the rest is the instruction
    return body.toLowerCase();
  }, [query]);
  const commandMatches = useMemo<CommandSpec[]>(() => {
    if (commandToken === null) return [];
    // No cap: the palette is scrollable, so every command is reachable. Typing a
    // prefix narrows the list.
    return searchCommands(commandToken);
  }, [commandToken]);
  const commandMenuOpen = commandToken !== null && commandMatches.length > 0;
  useEffect(() => { setCommandHighlight(0); }, [commandToken]);

  // Keep the keyboard-highlighted option visible as the user arrows through a
  // long, scrollable palette (otherwise the list scrolls but never follows).
  const commandListRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = commandListRef.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    el?.scrollIntoView({ block: 'nearest' });
  }, [commandHighlight, commandMenuOpen]);

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
    if (!m) return null;
    const tok = m[1].toLowerCase();
    return searchCommands(tok, { includeUnavailable: true }).find(
      (c) => c.name === tok || c.aliases.includes(tok),
    ) ?? null;
  }, [query]);

  // ── Bot / group `@mention` palette ──────────────────────────────────────
  // Typing `@word` (start of text or after a space, no space yet) opens a menu of
  // the user's bots and group chats. Selecting one inserts `@Name `; on send a
  // mentioned target receives the turn (delegation). Inert without `mentionTargets`.
  useHydrateBotAvatars();
  const mentionAvatars = useBotAvatarStore((s) => s.avatars);
  const [mentionHighlight, setMentionHighlight] = useState(0);
  const mentionToken = useMemo(() => mentionTokenOf(query), [query]);
  const mentionMatches = useMemo<MentionTarget[]>(() => {
    if (mentionToken === null || !mentionTargets || mentionTargets.length === 0) return [];
    return searchMentions(mentionTargets, mentionToken, MAX_MENTION_RESULTS);
  }, [mentionToken, mentionTargets]);
  const mentionMenuOpen = mentionToken !== null && mentionMatches.length > 0;
  useEffect(() => { setMentionHighlight(0); }, [mentionToken]);

  const mentionListRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = mentionListRef.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    el?.scrollIntoView({ block: 'nearest' });
  }, [mentionHighlight, mentionMenuOpen]);

  const completeMention = useCallback(
    (m: MentionTarget) => {
      // Replace only the partial token being typed; never clobber earlier text.
      setQuery(query.replace(/@([\w.-]*)$/, `@${m.name} `));
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    [setQuery, query],
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
    // The `@` palette takes priority: arrows navigate it and Enter/Tab completes
    // the highlighted mention (instead of sending).
    if (mentionMenuOpen && !e.nativeEvent.isComposing) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setMentionHighlight((h) => (h + 1) % mentionMatches.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setMentionHighlight((h) => (h - 1 + mentionMatches.length) % mentionMatches.length);
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        completeMention(mentionMatches[mentionHighlight]);
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
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!busy) onSend(e);
    }
  };

  const filled = Math.max(0, Math.min(1, contextFraction ?? 0));
  const commandSummary = useCallback(
    (c: CommandSpec) => (c.summaryKey ? t(c.summaryKey) : c.summary),
    [t],
  );

  // The `/` palette is PORTALED to <body> so its backdrop blur samples the real
  // page instead of a scoped backdrop root (the app shell's glass surfaces),
  // which would silently flatten the frost. Its box is tracked to the composer.
  const formRef = useRef<HTMLFormElement>(null);
  const [paletteBox, setPaletteBox] = useState<{ left: number; width: number; bottom: number } | null>(null);
  useLayoutEffect(() => {
    if (!commandMenuOpen && !mentionMenuOpen) {
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
  }, [commandMenuOpen, mentionMenuOpen]);

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
      <TradeApprovalBanner onCancel={onCancel} />
      {attachments && attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5" aria-label="Attached documents">
          {attachments.map((file) => (
            <span
              key={file.name}
              className="group inline-flex max-w-[70vw] sm:max-w-[240px] items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 py-1 pl-2 pr-1 text-[11px] text-foreground/90"
              title={file.name}
            >
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
                  className="min-w-0 truncate text-left hover:underline"
                >
                  {file.name}
                </button>
              ) : (
                <span className="min-w-0 truncate">{file.name}</span>
              )}
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
          ))}
        </div>
      )}
      {activeCommand && (
        <div className="mb-2 flex items-center gap-1.5">
          <span
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium',
              isCommandAvailable(activeCommand)
                ? 'border-primary/30 bg-primary/10 text-primary'
                : 'border-amber-400/30 bg-amber-400/10 text-amber-300',
            )}
          >
            <Command size={11} className="shrink-0" />
            {commandSummary(activeCommand)}
            {!isCommandAvailable(activeCommand) && (
              <span className="ml-1 text-[9px] uppercase tracking-wide opacity-80">not available</span>
            )}
          </span>
        </div>
      )}
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
      {commandMenuOpen && paletteBox && typeof document !== 'undefined' &&
        createPortal(
          <div
            ref={commandListRef}
            role="listbox"
            aria-label={t('code.command.paletteLabel')}
            style={{
              position: 'fixed',
              left: paletteBox.left,
              width: paletteBox.width,
              bottom: paletteBox.bottom,
            }}
            className="z-[120] max-h-[50vh] overflow-y-auto rounded-2xl glass-command-popover shadow-lg"
          >
          <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wide text-muted-foreground/60">
            {t('code.command.paletteLabel')}
          </div>
          {commandMatches.map((c, i) => {
            const available = isCommandAvailable(c);
            const hint = commandArgHint(c);
            return (
              <button
                key={c.name}
                type="button"
                role="option"
                aria-selected={i === commandHighlight}
                aria-disabled={!available}
                onMouseEnter={() => setCommandHighlight(i)}
                // onMouseDown (not onClick) so the textarea does not blur/lose the
                // selection before the command is inserted.
                onMouseDown={(e) => { e.preventDefault(); completeCommand(c); }}
                className={cn(
                  'flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors',
                  i === commandHighlight ? 'bg-accent/40' : 'hover:bg-accent/25',
                  !available && 'opacity-60',
                )}
              >
                <Command size={13} className={cn('shrink-0', available ? 'text-primary' : 'text-amber-400/70')} />
                <span className="font-mono text-xs">/{c.name}</span>
                {hint && <span className="hidden font-mono text-[10px] text-muted-foreground/50 sm:inline">{hint}</span>}
                <span className="ml-1 min-w-0 flex-1 truncate text-[11px] text-muted-foreground">
                  {commandSummary(c)}
                </span>
                <span className="shrink-0 rounded-full bg-accent/30 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground/60">
                  {c.category}
                </span>
                {!available && (
                  <span className="shrink-0 text-[9px] uppercase tracking-wide text-amber-400/70">soon</span>
                )}
              </button>
            );
          })}
          </div>,
          document.body,
        )}
      {mentionMenuOpen && paletteBox && typeof document !== 'undefined' &&
        createPortal(
          <div
            ref={mentionListRef}
            role="listbox"
            aria-label={t('bots.mentions.paletteLabel')}
            style={{
              position: 'fixed',
              left: paletteBox.left,
              width: paletteBox.width,
              bottom: paletteBox.bottom,
            }}
            className="z-[120] max-h-[50vh] overflow-y-auto rounded-2xl glass-command-popover shadow-lg"
          >
            <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wide text-muted-foreground/60">
              {t('bots.mentions.paletteLabel')}
            </div>
            {mentionMatches.map((m, i) => (
              <button
                key={`${m.kind}:${m.id}`}
                type="button"
                role="option"
                aria-selected={i === mentionHighlight}
                onMouseEnter={() => setMentionHighlight(i)}
                // onMouseDown (not onClick) so the textarea does not blur/lose the
                // selection before the mention is inserted.
                onMouseDown={(e) => { e.preventDefault(); completeMention(m); }}
                className={cn(
                  'flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors',
                  i === mentionHighlight ? 'bg-accent/40' : 'hover:bg-accent/25',
                )}
              >
                {m.kind === 'group'
                  ? <GhostAvatar spec={ghostSpecFromId(m.id)} size={18} title={m.name} />
                  : <BotAvatar botId={m.id} spec={avatarFor(mentionAvatars, m.id)} size={18} title={m.name} />}
                <span className="min-w-0 shrink-0 truncate font-medium">@{m.name}</span>
                {m.description && (
                  <span className="hidden min-w-0 flex-1 truncate text-[11px] text-muted-foreground/70 sm:inline">
                    {m.description}
                  </span>
                )}
                <span className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full bg-accent/30 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground/70">
                  {m.kind === 'group' ? <Users size={9} /> : <Bot size={9} />}
                  {m.kind}
                </span>
              </button>
            ))}
          </div>,
          document.body,
        )}
      <form ref={formRef} onSubmit={onSend} aria-busy={busy} className="relative flex flex-col w-full glass-composer border border-white/10 dark:border-white/5 rounded-3xl px-1.5 sm:px-3 py-1.5 shadow-lg shadow-black/20 focus-within:border-primary transition-colors overflow-visible">
        <textarea 
          ref={textareaRef}
          rows={1}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={placeholder}
          autoFocus={autoFocus}
          aria-label="Message Eclipse"
          // Keep the placeholder on ONE line while the composer is empty so it
          // clips cleanly instead of wrapping into a tall block on mobile.
          // Typed content returns to normal soft-wrapping (and auto-grow).
          wrap={query.length === 0 ? 'off' : 'soft'}
          className="chat-composer-scroll w-full bg-transparent border-0 outline-none resize-none overflow-x-hidden overflow-y-hidden placeholder:text-muted-foreground text-foreground px-2 sm:px-2.5 pt-2 pb-1 text-sm leading-relaxed min-w-0 focus:outline-none focus:ring-0"
        />
        
        <div className="flex min-w-0 items-end justify-between gap-2 px-0.5">
          <DropdownMenu>
            <DropdownMenuTrigger
              disabled={attaching}
              title="Add context, media or a tool"
              aria-label="Add context, media or a tool"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-0 focus-visible:outline-none disabled:opacity-50"
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
          <div className="flex min-w-0 items-center justify-end gap-1 sm:gap-2">
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
            <VoiceInputButton
              onTranscript={insertVoiceText}
              onStart={captureVoiceSelection}
              className="h-8 w-8"
            />
            {busy ? (
              <Button
                type="button"
                size="icon"
                onClick={onCancel}
                title="Stop generating"
                aria-label="Stop generating"
                className="p-1.5 bg-foreground/90 text-background hover:bg-foreground rounded-full shrink-0 h-8 w-8 cursor-pointer transition-colors flex items-center justify-center focus-visible:ring-0 focus-visible:outline-none"
              >
                <Pause size={15} fill="currentColor" />
              </Button>
            ) : (
              <Button 
                type="submit" 
                size="icon" 
                disabled={!query.trim() && !(attachments && attachments.length > 0)}
                className="p-1.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-full shrink-0 h-8 w-8 cursor-pointer disabled:opacity-40 disabled:hover:bg-primary transition-opacity flex items-center justify-center focus-visible:ring-0 focus-visible:outline-none"
              >
                <ArrowUp size={17} />
              </Button>
            )}
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

/**
 * The composer's model selector. ALWAYS rendered (never gated on a non-empty
 * list) so a model can be changed even before settings/catalog finish loading.
 * A submenu switches provider (with the key status the server reported), the
 * top level switches model on the active provider, and a "Custom model id…"
 * item types any id. A local/router provider gets a live discovery action.
 */
export function ModelSelector({ state }: { state: ChatModelState }) {
  const [customOpen, setCustomOpen] = useState(false);
  const [custom, setCustom] = useState("");
  // The menu is controlled so opening the Manage-models dialog can CLOSE it
  // first — otherwise the dialog opens behind the still-open `z-[110]` menu and
  // the click looks like it did nothing.
  const [menuOpen, setMenuOpen] = useState(false);
  const label = state.displayModel || state.providerLabel || "Model";
  const current = state.providers.find((p) => p.id === state.selectedProvider);
  // Prefer the provider's own id; fall back to whichever provider owns the
  // selected model, then the label (resolved by ProviderLogo).
  const logoProvider =
    state.selectedProvider ||
    state.providers.find((p) => p.models.includes(state.selectedModel))?.id ||
    current?.id ||
    state.providerLabel;
  useHydrateEnabledModels();
  const enabledFor = useEnabledModelsStore((s) => s.enabledFor);
  const isCurated = useEnabledModelsStore((s) => s.isCurated);

  const submitCustom = () => {
    const v = custom.trim();
    if (v) state.setModel(v);
    setCustom("");
    setCustomOpen(false);
  };

  return (
    <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
      <DropdownMenuTrigger
        title={`Model: ${state.displayModel || "default"} · provider ${state.providerLabel}`}
        className="inline-flex min-w-0 items-center gap-1.5 px-2.5 py-1 h-7 max-w-none sm:max-w-[180px] sm:px-3 rounded-full bg-accent/25 border border-border/25 text-muted-foreground hover:text-foreground hover:border-border/40 text-xs font-medium whitespace-nowrap transition-colors cursor-pointer"
      >
        <ProviderLogo provider={logoProvider} size={13} className="text-primary" />
        <span className="hidden min-w-0 truncate font-mono sm:inline">{label}</span>
        <ChevronDown size={13} className="shrink-0 opacity-70" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72 max-w-[calc(100vw-1.5rem)]">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="flex items-center justify-between gap-2">
            <span>Model</span>
            <span className="text-[10px] font-normal text-muted-foreground truncate">{state.providerLabel}</span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <div className="max-h-64 overflow-y-auto">
          {state.loading && (state.providers.length === 0) && (
            <div className="px-2 py-1.5 text-[11px] text-muted-foreground flex items-center gap-2">
              <Loader2 size={12} className="animate-spin" /> Loading models…
            </div>
          )}
          {(() => {
            // Every provider the operator can use right now (a keyless local
            // server, or a key that resolves from env/vault). Models from ALL of
            // them are listed — the active provider first — so a second
            // connected provider is usable directly, without first switching the
            // active provider. Selecting a model here switches the active
            // provider to that model's provider.
            const usable = state.providers.filter((p) => p.keyless || p.available);
            const ordered = [
              ...state.providers.filter((p) => p.id === state.selectedProvider),
              ...usable.filter((p) => p.id !== state.selectedProvider),
            ];
            // Fall back to the current provider alone when none report usable
            // (runtime/settings not ready) so the menu is never empty.
            const groups = ordered.length ? ordered : (current ? [current] : []);
            if (groups.length === 0) {
              return !state.loading ? (
                <div className="px-2 py-1.5 text-[11px] text-muted-foreground">No declared models</div>
              ) : null;
            }
            return groups.map((p) => {
              const all = p.models ?? [];
              // Only the ENABLED (or, when uncurated, a capped slice) reach the
              // menu, so a provider listing hundreds of models never floods it.
              const curated = isCurated(p.id);
              const { models, truncated } = compactModels(p.id, all, {
                explicitEnabled: curated ? enabledFor(p.id) : null,
                selected: p.id === state.selectedProvider ? state.selectedModel : undefined,
              });
              const list =
                p.id === state.selectedProvider && state.selectedModel && !models.includes(state.selectedModel)
                  ? [state.selectedModel, ...models]
                  : models;
              const manageable = all.length > 0 && (curated || truncated || all.length > 1);
              if (list.length === 0 && !manageable) return null;
              return (
                <div key={p.id}>
                  <DropdownMenuLabel className="flex items-center justify-between gap-2">
                    <span className="truncate">{p.label}</span>
                    <span className="flex items-center gap-1.5">
                      {p.keyless ? (
                        <span className="text-[9px] font-normal text-muted-foreground/60">local</span>
                      ) : p.available ? (
                        <span className="text-[9px] font-normal text-emerald-400/70">key set</span>
                      ) : null}
                      {manageable && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            // Close the menu FIRST so the dialog is not rendered
                            // behind it; then open the curation dialog.
                            setMenuOpen(false);
                            state.openManageModels(p.id);
                          }}
                          className="inline-flex items-center gap-0.5 text-[9px] font-medium text-muted-foreground/70 hover:text-foreground cursor-pointer"
                          title={`Manage ${p.label} models`}
                        >
                          <Layers size={10} /> Manage
                        </button>
                      )}
                    </span>
                  </DropdownMenuLabel>
                  {list.length === 0 && (
                    <div className="px-2 py-1.5 text-[10px] text-muted-foreground/70">
                      None enabled — open Manage to choose models.
                    </div>
                  )}
                  {list.map((m) => {
                    const selected = p.id === state.selectedProvider && m === state.selectedModel;
                    return (
                      <DropdownMenuItem
                        key={`${p.id}:${m}`}
                        onClick={() => { if (!selected) state.select(p.id, m); }}
                        className="gap-2"
                      >
                        <Check size={13} className={cn("shrink-0", selected ? "opacity-100 text-primary" : "opacity-0")} />
                        <span className="font-mono truncate">{m}</span>
                      </DropdownMenuItem>
                    );
                  })}
                </div>
              );
            });
          })()}
          </div>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={!state.canDiscover}
          closeOnClick={false}
          onClick={() => {
            // Discover then immediately open Manage so the operator curates the
            // catalog instead of it being poured into the menu. Close the menu so
            // the dialog is not hidden behind it.
            setMenuOpen(false);
            void state.discoverProvider().finally(() => state.openManageModels());
          }}
          className="gap-2 text-primary/90"
        >
          {state.discovering
            ? <Loader2 size={13} className="shrink-0 animate-spin" />
            : <Layers size={13} className="shrink-0" />}
          Manage models…
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuSub>
          <DropdownMenuSubTrigger className="gap-2">
            <Cpu size={13} className="shrink-0" />
            <span>Provider</span>
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="w-64 max-w-[calc(100vw-1.5rem)]">
            <div className="max-h-72 overflow-y-auto">
              {state.providers.map((p) => (
                <DropdownMenuItem
                  key={p.id}
                  onClick={() => {
                    // A provider with no key cannot run — send the operator to
                    // Settings › AI, where the key is added, instead of selecting
                    // a provider that would fail. Keyless/configured providers
                    // select normally, adopting their first model so the choice
                    // is (provider, model) together — never a mismatched pair.
                    if (!p.keyless && !p.available) {
                      useCommandStore.getState().dispatch({ tab: "settings", subroute: "settings.ai" });
                      return;
                    }
                    state.select(p.id, p.models[0] ?? "");
                  }}
                  className="gap-2"
                >
                  <Check size={13} className={cn("shrink-0", p.id === state.selectedProvider ? "opacity-100 text-primary" : "opacity-0")} />
                  <ProviderLogo provider={p.id} size={13} className={p.id === state.selectedProvider ? "text-primary" : "text-muted-foreground"} />
                  <span className="truncate">{p.label}</span>
                  {p.keyless ? (
                    <span className="ml-auto text-[9px] text-muted-foreground/50">no key</span>
                  ) : p.available ? (
                    <span className="ml-auto text-[9px] text-emerald-400/70">key set</span>
                  ) : (
                    <span className="ml-auto inline-flex items-center gap-1 text-[9px] font-medium text-primary/90">
                      <KeyRound size={10} /> Add key
                    </span>
                  )}
                </DropdownMenuItem>
              ))}
            </div>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuGroup>
          {state.error && (
            <div className="px-2 py-1 text-[10px] text-rose-400/90">{state.error}</div>
          )}
          {customOpen ? (
            <div className="flex items-center gap-1.5 px-1.5 py-1">
              <input
                autoFocus
                value={custom}
                onChange={(e) => setCustom(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    submitCustom();
                  }
                }}
                placeholder="model id"
                className="min-w-0 flex-1 rounded-md bg-background/60 border border-border/30 px-2 py-1 text-xs font-mono outline-none focus:border-primary"
              />
              <button
                type="button"
                onClick={submitCustom}
                className="rounded-md px-2 py-1 text-[11px] text-primary hover:bg-accent"
              >
                Use
              </button>
            </div>
          ) : (
            <DropdownMenuItem
              closeOnClick={false}
              onClick={() => setCustomOpen(true)}
              className="gap-2"
            >
              <Plus size={13} className="shrink-0" />
              <span>Custom model id…</span>
            </DropdownMenuItem>
          )}
        </DropdownMenuGroup>
      </DropdownMenuContent>
      {state.manageTarget && (
        <ManageModelsDialog
          providerId={state.manageTarget.id}
          providerLabel={state.manageTarget.label}
          allModels={state.manageTarget.models ?? []}
          selected={state.selectedProvider === state.manageTarget.id ? state.selectedModel : undefined}
          onDiscover={() => state.discoverProvider(state.manageTarget!.id)}
          canDiscover={state.canDiscover}
          onClose={state.closeManageModels}
        />
      )}
    </DropdownMenu>
  );
}
