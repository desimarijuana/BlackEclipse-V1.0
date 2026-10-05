'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Plus, Mic, ArrowUp, Pause, Loader2, Sparkles, FileText, X, ChevronDown, Check, Cpu, KeyRound, Layers } from '@/lib/icons';
import { Button } from '@/components/ui/button';
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

// Grow the composer to roughly four lines, then scroll instead of growing.
const MAX_HEIGHT = 120;

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
  /** The assistant is working: submit becomes a pause (cancel) button. */
  busy?: boolean;
  /** Called when the user clicks pause. */
  onCancel?: () => void;
  /** Opens the file picker — the "+" is the attach-documents affordance. */
  onAttach?: () => void;
  /** Shows a spinner on the "+" while documents upload. */
  attaching?: boolean;
  /**
   * Attached documents rendered as visible chips above the composer, so an
   * attachment is obviously present without expanding anything. Removing a chip
   * calls `onRemoveAttachment` with its name.
   */
  attachments?: AttachmentChip[];
  onRemoveAttachment?: (name: string) => void;
  /**
   * A short "context used" label (e.g. `4.2k / 60k`). Rendered quietly under
   * the composer; omitted when there is nothing to report.
   */
  contextLabel?: string;
  /** 0–1 fraction for the small usage meter. */
  contextFraction?: number;
}

export function ChatInput({ 
  query, 
  setQuery, 
  onSend, 
  placeholder = "Ask about a stock, sector, or market trend...", 
  autoFocus,
  showProvider = true,
  modelState,
  busy = false,
  onCancel,
  onAttach,
  attaching = false,
  attachments,
  onRemoveAttachment,
  contextLabel,
  contextFraction,
  }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // The REAL configured provider, never a fabricated model list.
  const providerLabel = useMemo(() => getAgentProvider().label, []);

  // Auto-grow the composer with its content up to a cap, then scroll. A long
  // prompt no longer stays clipped on one line.
  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const needed = el.scrollHeight;
    el.style.height = `${Math.min(needed, MAX_HEIGHT)}px`;
    // Only show a scrollbar once the content truly exceeds the cap; otherwise a
    // 1px rounding gap would render a full-height thumb next to the buttons.
    el.style.overflowY = needed > MAX_HEIGHT ? 'auto' : 'hidden';
  }, []);

  useEffect(() => { resize(); }, [query, resize]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter inserts a newline. Ignore IME composition.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!busy) onSend(e);
    }
  };

  const filled = Math.max(0, Math.min(1, contextFraction ?? 0));

  return (
    <div className="w-full">
      {attachments && attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5" aria-label="Attached documents">
          {attachments.map((file) => (
            <span
              key={file.name}
              className="group inline-flex max-w-[240px] items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 py-1 pl-2 pr-1 text-[11px] text-foreground/90"
              title={file.name}
            >
              {file.uploading ? (
                <Loader2 size={12} className="shrink-0 animate-spin text-primary" />
              ) : (
                <FileText size={12} className="shrink-0 text-primary" />
              )}
              <span className="min-w-0 truncate">{file.name}</span>
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
      <form onSubmit={onSend} aria-busy={busy} className="relative flex items-end w-full glass-card border border-white/10 dark:border-white/5 rounded-3xl px-1.5 sm:px-3 py-1 shadow-lg shadow-black/20 focus-within:border-primary focus-within:glass-card transition-colors overflow-hidden">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onAttach}
          disabled={attaching}
          title="Add documents as context"
          aria-label="Add documents as context"
          className="flex text-muted-foreground hover:text-foreground rounded-full hover:bg-accent shrink-0 h-8 w-8 mb-0.5 focus-visible:ring-0 focus-visible:outline-none"
        >
          {attaching ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
        </Button>
        
        <textarea 
          ref={textareaRef}
          rows={1}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          autoFocus={autoFocus}
          aria-label="Message Eclipse"
          className="chat-composer-scroll flex-1 self-center bg-transparent border-0 outline-none resize-none overflow-y-hidden placeholder:text-muted-foreground text-foreground pl-3 sm:pl-4 pr-4 sm:pr-5 py-2 text-sm leading-relaxed min-w-0 w-full focus:outline-none focus:ring-0"
        />
        
        <div className="flex items-center gap-1 sm:gap-2 shrink-0 mb-0.5">
          {modelState ? (
            <ModelSelector state={modelState} />
          ) : showProvider ? (
            /* The real configured provider — not a fabricated model picker. */
            <span
              className="hidden min-[400px]:inline-flex items-center gap-1.5 px-3 py-1 h-7 rounded-full bg-accent/25 border border-border/25 text-muted-foreground text-xs font-medium whitespace-nowrap"
              title={`Chat provider: ${providerLabel}`}
            >
              <Sparkles size={12} className="text-primary" />
              {providerLabel}
            </span>
          ) : null}
          <Button 
            type="button" 
            variant="ghost" 
            size="icon" 
            className="p-1.5 text-muted-foreground hover:text-foreground rounded-full hover:bg-accent shrink-0 h-8 w-8 focus-visible:ring-0 focus-visible:outline-none"
          >
            <Mic size={16} />
          </Button>
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
              disabled={!query.trim()}
              className="p-1.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-full shrink-0 h-8 w-8 cursor-pointer disabled:opacity-40 disabled:hover:bg-primary transition-opacity flex items-center justify-center focus-visible:ring-0 focus-visible:outline-none"
            >
              <ArrowUp size={17} />
            </Button>
          )}
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
function ModelSelector({ state }: { state: ChatModelState }) {
  const [customOpen, setCustomOpen] = useState(false);
  const [custom, setCustom] = useState("");
  const label = state.displayModel || state.providerLabel || "Model";
  const current = state.providers.find((p) => p.id === state.selectedProvider);
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
    <DropdownMenu>
      <DropdownMenuTrigger
        title={`Model: ${state.displayModel || "default"} · provider ${state.providerLabel}`}
        className="inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1 h-7 max-w-[180px] rounded-full bg-accent/25 border border-border/25 text-muted-foreground hover:text-foreground hover:border-border/40 text-xs font-medium whitespace-nowrap transition-colors cursor-pointer"
      >
        <Sparkles size={12} className="text-primary shrink-0" />
        <span className="truncate font-mono">{label}</span>
        <ChevronDown size={13} className="shrink-0 opacity-70" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
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
                          onClick={(e) => { e.preventDefault(); e.stopPropagation(); state.openManageModels(p.id); }}
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
            // catalog instead of it being poured into the menu.
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
          <DropdownMenuSubContent className="w-64">
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
