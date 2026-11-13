'use client';

// The composer's model selector. Extracted from `chat-input.tsx` so the
// composer file stays under the size ceiling; `chat-input` re-exports it, so
// every existing import path keeps working.

import { useState } from 'react';
import { Plus, ChevronDown, Check, Cpu, KeyRound, Layers, Loader2 } from '@/lib/icons';
import { ProviderLogo } from '@/components/providers/provider-logo';
import { ManageModelsDialog } from '@/components/screens/manage-models-dialog';
import { useCommandStore } from '@/lib/search/store';
import { compactModels, useEnabledModelsStore, useHydrateEnabledModels } from '@/lib/agent/enabled-models';
import type { ChatModelState } from '@/lib/agent/use-chat-model';
import { cn } from '@/lib/utils';
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

