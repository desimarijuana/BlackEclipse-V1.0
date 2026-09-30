"use client";

// ── MCP server editor (Phase 6.1) ───────────────────────────────────────────
// The full-fidelity editor for the runtime's contract. Every field the runtime
// supports is reachable here; the save always sends every field it owns so a
// save can neither silently reset nor silently widen a server's authority.
// Discovery is not activation; every selection is explicit and reversible.

import { useState } from "react";
import { AlertCircle, Check, ChevronDown, Loader2, Plug, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { MCPEffect, MCPToolView, MCPTransport, MCPTrust } from "@/lib/harness/mcp-types";
import type { DraftServer } from "@/lib/harness/mcp-draft";
import { LIMIT_DEFAULTS } from "@/lib/harness/mcp-draft";
import { EffectBadge, Panel } from "./primitives";

const TEXTAREA = "rounded-xl border border-border/40 bg-background/60 px-3 py-2 text-xs font-mono text-foreground outline-none focus:border-primary/40";

function Section({ title, hint, children, defaultOpen = false }: { title: string; hint?: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-border/20 glass-card-subtle">
      <button type="button" className="flex w-full items-center justify-between px-3.5 py-2.5 cursor-pointer" onClick={() => setOpen((o) => !o)}>
        <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">{title}</span>
        <ChevronDown className={cn("w-3.5 h-3.5 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="px-3.5 pb-3.5 space-y-3">
          {hint && <p className="text-[10px] text-muted-foreground/70">{hint}</p>}
          {children}
        </div>
      )}
    </div>
  );
}

export function ServerEditor({
  draft,
  setDraft,
  onCancel,
  onSave,
  onTest,
  saving,
  testing,
  testResult,
}: {
  draft: DraftServer;
  setDraft: (d: DraftServer) => void;
  onCancel: () => void;
  onSave: () => void;
  onTest: () => void;
  saving: boolean;
  testing: boolean;
  testResult: { state: string; diagnostic?: string | null; tools: MCPToolView[] } | null;
}) {
  const set = (patch: Partial<DraftServer>) => setDraft({ ...draft, ...patch });
  const toggleTool = (name: string) => set({
    selectedTools: draft.selectedTools.includes(name)
      ? draft.selectedTools.filter((t) => t !== name)
      : [...draft.selectedTools, name],
  });
  const setEffect = (name: string, effect: MCPEffect | "") => {
    const next = { ...draft.toolEffects };
    if (effect === "") delete next[name];
    else next[name] = effect;
    set({ toolEffects: next });
  };
  const missing = !draft.id.trim() || (draft.transport === "stdio" ? !draft.command.trim() : !draft.url.trim());
  const isRemote = draft.transport === "http" || draft.transport === "sse";
  const discovered = testResult?.tools ?? [];
  const effectsOn = draft.selectedTools;

  return (
    <Panel className="p-5 space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Server ID</Label>
          <Input value={draft.id} onChange={(e) => set({ id: e.target.value })} placeholder="e.g. finance-tools" className="rounded-xl font-mono text-xs" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Display name (optional)</Label>
          <Input value={draft.name} onChange={(e) => set({ name: e.target.value })} placeholder="defaults to the id" className="rounded-xl text-xs" />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label className="text-xs text-muted-foreground font-medium">Transport</Label>
        <Select value={draft.transport} onValueChange={(v) => set({ transport: (v ?? "stdio") as MCPTransport })}>
          <SelectTrigger className="h-9 rounded-xl text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="stdio">stdio — local subprocess</SelectItem>
            <SelectItem value="http">http — remote Streamable HTTP</SelectItem>
            <SelectItem value="sse">sse — remote Server-Sent Events</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-[10px] text-muted-foreground/70">
          Streamable HTTP is the current remote transport; SSE is the older HTTP+Server-Sent-Events endpoint. Both
          share the same SSRF check, auth and lifecycle.
        </p>
      </div>

      {isRemote ? (
        <>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Endpoint URL</Label>
            <Input value={draft.url} onChange={(e) => set({ url: e.target.value })} placeholder="https://mcp.example.com/mcp" className="rounded-xl font-mono text-xs" />
            <p className="text-[10px] text-muted-foreground/70">Must be https (loopback http is allowed for local testing). Private hosts are refused.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs text-muted-foreground font-medium">Auth kind</Label>
              <Select value={draft.authKind} onValueChange={(v) => set({ authKind: (v ?? "header") as DraftServer["authKind"] })}>
                <SelectTrigger className="h-9 rounded-xl text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="header">Header</SelectItem>
                  <SelectItem value="query">Query param</SelectItem>
                  <SelectItem value="oauth">OAuth 2.1 (sign in)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {draft.authKind !== "oauth" && (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs text-muted-foreground font-medium">Name</Label>
                  <Input value={draft.authName} onChange={(e) => set({ authName: e.target.value })} placeholder="Authorization" className="rounded-xl font-mono text-xs" />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs text-muted-foreground font-medium">Value prefix</Label>
                  <Input value={draft.authPrefix} onChange={(e) => set({ authPrefix: e.target.value })} placeholder="Bearer " className="rounded-xl font-mono text-xs" />
                </div>
              </>
            )}
          </div>
          {draft.authKind === "oauth" ? (
            <p className="text-[10px] text-muted-foreground/70">
              This server manages its own OAuth 2.1 sign-in; no vault secret is stored here. After saving, use
              <span className="font-mono"> Sign in</span> on the server card and complete the device flow.
            </p>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs text-muted-foreground font-medium">Vault secret name</Label>
              <Input value={draft.authSecretRef} onChange={(e) => set({ authSecretRef: e.target.value })} placeholder="e.g. notion_integration_token" className="rounded-xl font-mono text-xs" />
              <p className="text-[10px] text-muted-foreground/70">The token is stored encrypted in the Secret vault; only its name is kept here.</p>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Command</Label>
            <Input value={draft.command} onChange={(e) => set({ command: e.target.value })} placeholder="e.g. npx or python" className="rounded-xl font-mono text-xs" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Arguments (one per line)</Label>
            <textarea value={draft.argsText} onChange={(e) => set({ argsText: e.target.value })} rows={3} placeholder={"-y\n@modelcontextprotocol/server-filesystem\n/path/to/dir"} className={TEXTAREA} />
            <p className="text-[10px] text-muted-foreground/70">Passed as an argv list — never through a shell.</p>
          </div>
        </>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Environment (KEY=VALUE per line)</Label>
          <textarea value={draft.envText} onChange={(e) => set({ envText: e.target.value })} rows={3} placeholder={draft.envKeys.length ? `${draft.envKeys[0]}=` : "API_BASE_URL=https://…"} className={TEXTAREA} />
          <p className="text-[10px] text-muted-foreground/70">
            Scoped to this server only. Leave the value blank (<span className="font-mono">KEY=</span>) to keep the stored secret.
            {draft.envKeys.length > 0 && <> Stored keys: <span className="font-mono">{draft.envKeys.join(", ")}</span>.</>}
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Host env vars to pass through (optional)</Label>
          <Input value={draft.envAllowlistText} onChange={(e) => set({ envAllowlistText: e.target.value })} placeholder="e.g. FOO BAR" className="rounded-xl font-mono text-xs" />
          <p className="text-[10px] text-muted-foreground/70">Names copied from the host environment into the server. Nothing else is forwarded.</p>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label className="text-xs text-muted-foreground font-medium">Vault secret references (ENV_VAR=secretName per line)</Label>
        <textarea value={draft.secretRefsText} onChange={(e) => set({ secretRefsText: e.target.value })} rows={2} placeholder="API_TOKEN=my_server_token" className={TEXTAREA} />
        <p className="text-[10px] text-muted-foreground/70">Preferred over an inline value: the secret is stored encrypted in the vault and resolved at spawn.</p>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label className="text-xs text-muted-foreground font-medium">Working directory (optional)</Label>
        <Input value={draft.cwd} onChange={(e) => set({ cwd: e.target.value })} placeholder="relative to the app root" className="rounded-xl font-mono text-xs" />
      </div>

      {testResult && (
        <p className={cn("text-[11px] flex items-center gap-1", testResult.state === "connected" ? "text-emerald-400" : "text-rose-400")}>
          {testResult.state === "connected" ? <Check className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
          {testResult.state === "connected" ? `Connected · ${testResult.tools.length} tool(s) discovered` : testResult.diagnostic || "Connection failed"}
        </p>
      )}

      {/* ── Trust ─────────────────────────────────────────────────────────── */}
      <Section title="Trust tier" hint="An untrusted server needs a per-call approval for every non-read call, and its own annotations can never activate a tool.">
        <div className="flex items-center gap-2">
          {(["full", "untrusted"] as MCPTrust[]).map((t) => (
            <button
              key={t} type="button" onClick={() => set({ trust: t })}
              className={cn("rounded-xl border px-3 py-1.5 text-[11px] cursor-pointer",
                draft.trust === t
                  ? t === "untrusted" ? "border-rose-500/50 bg-rose-500/15 text-rose-300" : "border-primary/50 bg-primary/15 text-primary"
                  : "border-border/30 text-muted-foreground hover:bg-accent/20")}
            >
              {t === "full" ? "Full (operator-declared effects apply)" : "Untrusted (approval for every non-read call)"}
            </button>
          ))}
        </div>
      </Section>

      {/* ── Tool selection ────────────────────────────────────────────────── */}
      <Section title="Enabled tools" hint="Discovery is not activation. An empty include selects nothing." defaultOpen>
        <div className="flex items-center gap-2">
          {(["list", "include-exclude"] as const).map((m) => (
            <button key={m} type="button" onClick={() => set({ filterMode: m })}
              className={cn("rounded-lg border px-2.5 py-1 text-[10px] cursor-pointer",
                draft.filterMode === m ? "border-primary/50 bg-primary/15 text-primary" : "border-border/30 text-muted-foreground")}>
              {m === "list" ? "Exact list" : "Include / exclude globs"}
            </button>
          ))}
        </div>
        {draft.filterMode === "include-exclude" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs text-muted-foreground font-medium">Include globs (one per line)</Label>
              <textarea value={draft.includeText} onChange={(e) => set({ includeText: e.target.value })} rows={3} placeholder={"get_*\nlist_*"} className={TEXTAREA} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs text-muted-foreground font-medium">Exclude globs (one per line)</Label>
              <textarea value={draft.excludeText} onChange={(e) => set({ excludeText: e.target.value })} rows={3} placeholder="*_secret" className={TEXTAREA} />
            </div>
            <p className="text-[10px] text-muted-foreground/70 sm:col-span-2">Include wins over exclude; an empty include selects nothing.</p>
          </div>
        ) : effectsOn.length === 0 && discovered.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/70">Test the connection to list tools, or switch to globs to select by pattern.</p>
        ) : null}

        {draft.filterMode === "list" && discovered.length > 0 && (
          <div className="rounded-xl border border-border/20 divide-y divide-border/10 max-h-72 overflow-y-auto">
            {discovered.map((tool) => {
              const activatable = !tool.diagnostic;
              const checked = draft.selectedTools.includes(tool.originalName);
              const effect = draft.toolEffects[tool.originalName] ?? tool.effect;
              return (
                <div key={tool.originalName} className="flex items-start gap-3 px-3 py-2.5">
                  <input type="checkbox" className="mt-0.5 accent-primary" checked={checked} disabled={!activatable}
                    onChange={() => activatable && toggleTool(tool.originalName)} />
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-mono text-foreground">{tool.originalName}</span>
                      <EffectBadge effect={effect} />
                      {tool.effectSource && <span className="text-[9px] font-mono text-muted-foreground">{tool.effectSource}</span>}
                      {tool.diagnostic && <span className="text-[10px] text-rose-400">{tool.diagnostic}</span>}
                    </div>
                    {tool.description && <p className="text-[10px] text-muted-foreground line-clamp-2">{tool.description}</p>}
                    <div className="flex items-center gap-1.5">
                      <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Effect</span>
                      <Select value={(draft.toolEffects[tool.originalName] as string | undefined) ?? "__unset__"} onValueChange={(v: string | null) => setEffect(tool.originalName, !v || v === "__unset__" ? "" : (v as MCPEffect))}>
                        <SelectTrigger className="h-6 rounded-lg text-[10px] w-40"><SelectValue placeholder="(unset)" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__unset__">(unset — use the server hint)</SelectItem>
                          <SelectItem value="read">read</SelectItem>
                          <SelectItem value="write">write</SelectItem>
                          <SelectItem value="external_action">external_action</SelectItem>
                          <SelectItem value="unknown">unknown</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        <p className="text-[10px] text-muted-foreground/70">
          A tool effect you declare is trusted; a tool&apos;s own annotation is not. `write` / `external_action` are
          enabled only when you add them below and then approve each exact call.
        </p>
        <div className="flex items-center gap-4 flex-wrap">
          {(["read", "write", "external_action"] as MCPEffect[]).map((eff) => (
            <label key={eff} className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" className="accent-primary" checked={draft.enabledEffects.includes(eff)} disabled={eff === "read"}
                onChange={() => set({
                  enabledEffects: draft.enabledEffects.includes(eff)
                    ? draft.enabledEffects.filter((e) => e !== eff)
                    : [...draft.enabledEffects, eff],
                })} />
              <EffectBadge effect={eff} />
            </label>
          ))}
        </div>
      </Section>

      {/* ── Data sources ──────────────────────────────────────────────────── */}
      <Section title="Native data sources" hint="A declared data tool can be considered by native retrieval planning, but its results stay external and are never Eclipse-verified.">
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">tool=dataType per line (selected read tools only)</Label>
          <textarea value={draft.dataSourcesText} onChange={(e) => set({ dataSourcesText: e.target.value })} rows={2} placeholder="get_quote=current_quote" className={TEXTAREA} />
          <p className="text-[10px] text-muted-foreground/70">
            Offer this only for a selected read-effect tool. An undeclared tool stays directly callable.
          </p>
        </div>
      </Section>

      {/* ── Capabilities ──────────────────────────────────────────────────── */}
      <Section title="Capabilities (resources / prompts)">
        <div className="flex items-center gap-4 flex-wrap">
          <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
            <input type="checkbox" className="accent-primary" checked={draft.resourcesEnabled} onChange={(e) => set({ resourcesEnabled: e.target.checked })} />
            Expose resources
          </label>
          <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
            <input type="checkbox" className="accent-primary" checked={draft.promptsEnabled} onChange={(e) => set({ promptsEnabled: e.target.checked })} />
            Expose prompts
          </label>
        </div>
        <p className="text-[10px] text-muted-foreground/70">
          Registered only if the live server advertises the capability AND you enable it here. A disabled capability
          might be either not advertised by this server or switched off by you.
        </p>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Allowed resource URI schemes (optional narrowing)</Label>
          <Input value={draft.resourceSchemesText} onChange={(e) => set({ resourceSchemesText: e.target.value })} placeholder="e.g. note, doc — leave blank for the default allowlist" className="rounded-xl font-mono text-xs" />
          <p className="text-[10px] text-muted-foreground/70">
            A comma-separated subset of the built-in allowlist. This can only REMOVE schemes, never add one; an
            unknown scheme has no effect.
          </p>
        </div>
      </Section>

      {/* ── Lifecycle ─────────────────────────────────────────────────────── */}
      <Section title="Lifecycle" hint="Leave a field blank for the default. A lazy server registers cached tool declarations and connects on the first call.">
        <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
          <input type="checkbox" className="accent-primary" checked={draft.lazy} onChange={(e) => set({ lazy: e.target.checked })} />
          Lazy start (register tools from the on-disk cache without connecting)
        </label>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Keepalive interval (s)</Label>
            <Input value={draft.keepaliveIntervalText} onChange={(e) => set({ keepaliveIntervalText: e.target.value })} placeholder="default: off (min 10)" className="rounded-xl font-mono text-xs" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Idle timeout (s)</Label>
            <Input value={draft.idleTimeoutText} onChange={(e) => set({ idleTimeoutText: e.target.value })} placeholder="default: off (min 30)" className="rounded-xl font-mono text-xs" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Max lifetime (s)</Label>
            <Input value={draft.maxLifetimeText} onChange={(e) => set({ maxLifetimeText: e.target.value })} placeholder="default: off (min 60)" className="rounded-xl font-mono text-xs" />
          </div>
        </div>
      </Section>

      {/* ── TLS ───────────────────────────────────────────────────────────── */}
      <Section title="TLS / client certificate">
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Certificate verification</Label>
          <Select value={draft.sslVerifyMode} onValueChange={(v) => set({ sslVerifyMode: (v ?? "true") as DraftServer["sslVerifyMode"] })}>
            <SelectTrigger className="h-9 rounded-xl text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="true">Verify (system trust store)</SelectItem>
              <SelectItem value="custom-ca">Verify against a custom CA bundle</SelectItem>
              <SelectItem value="false">Do not verify (insecure — testing only)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {draft.sslVerifyMode === "custom-ca" && (
          <Input value={draft.sslVerifyPath} onChange={(e) => set({ sslVerifyPath: e.target.value })} placeholder="path to a CA bundle (leave blank to keep the stored path)" className="rounded-xl font-mono text-xs" />
        )}
        {draft.sslVerifyMode === "false" && (
          <p className="text-[10px] text-rose-300">
            <ShieldAlert className="inline w-3 h-3 -mt-0.5" /> With verification off, a man-in-the-middle cannot be
            detected. Use only against a trusted loopback endpoint.
          </p>
        )}
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Client certificate (mTLS)</Label>
          <textarea
            value={draft.clientCertText}
            onChange={(e) => set({ clientCertText: e.target.value })}
            rows={3}
            placeholder={"combined PEM, or\ncert PEM\nkey PEM\npassphrase (optional)"}
            className={TEXTAREA}
          />
          <p className="text-[10px] text-muted-foreground/70">
            Accepts a combined PEM, a <span className="font-mono">[cert, key]</span> pair, or a
            <span className="font-mono"> [cert, key, passphrase]</span> triple, one per line.
            {draft.clientCertConfigured ? " A certificate is already stored; its value is never shown. Enter a new value to replace it." : ""}
          </p>
          {draft.clientCertConfigured && (
            <label className="flex items-center gap-2 text-xs text-rose-300 cursor-pointer">
              <input type="checkbox" className="accent-rose-400" checked={draft.clearClientCert} onChange={(e) => set({ clearClientCert: e.target.checked })} />
              Clear the stored client certificate and key
            </label>
          )}
        </div>
      </Section>

      {/* ── Limits ────────────────────────────────────────────────────────── */}
      <Section title="Limits" hint="Leave blank for the default. The runtime clamps each value to a documented floor/ceiling; the clamped value is shown on the card.">
        <div className="grid gap-3 sm:grid-cols-3">
          <LimitField label="Startup timeout (ms)" value={draft.startupTimeoutText} fallback={LIMIT_DEFAULTS.startupTimeoutMs} onChange={(v) => set({ startupTimeoutText: v })} />
          <LimitField label="Catalog timeout (ms)" value={draft.catalogTimeoutText} fallback={LIMIT_DEFAULTS.catalogTimeoutMs} onChange={(v) => set({ catalogTimeoutText: v })} />
          <LimitField label="Call timeout (ms)" value={draft.callTimeoutText} fallback={LIMIT_DEFAULTS.callTimeoutMs} onChange={(v) => set({ callTimeoutText: v })} />
          <LimitField label="Output limit (bytes)" value={draft.outputLimitText} fallback={LIMIT_DEFAULTS.outputLimitBytes} onChange={(v) => set({ outputLimitText: v })} />
          <LimitField label="Max concurrency (1–16)" value={draft.maxConcurrencyText} fallback={LIMIT_DEFAULTS.maxConcurrency} onChange={(v) => set({ maxConcurrencyText: v })} />
          <LimitField label="Max tools (≤500)" value={draft.maxToolsText} fallback={LIMIT_DEFAULTS.maxTools} onChange={(v) => set({ maxToolsText: v })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Pinned protocol version (optional)</Label>
          <Input value={draft.protocolVersion} onChange={(e) => set({ protocolVersion: e.target.value })} placeholder="e.g. 2025-11-25" className="rounded-xl font-mono text-xs" />
        </div>
      </Section>

      <div className="flex flex-col gap-1.5">
        <Label className="text-xs text-muted-foreground font-medium">Notes (optional)</Label>
        <Input value={draft.description} onChange={(e) => set({ description: e.target.value })} placeholder="why you connected this server (never used for authorization)" className="rounded-xl text-xs" />
      </div>

      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={onTest} disabled={missing || testing}>
          {testing ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Plug className="w-3.5 h-3.5 mr-1" />}
          Test connection
        </Button>
      </div>

      <div className="flex items-center justify-between gap-3 pt-1">
        <div className="flex items-center gap-2">
          <button
            role="switch" aria-checked={draft.enabled} type="button"
            onClick={() => set({ enabled: !draft.enabled })}
            className={cn("relative inline-flex h-5 w-9 shrink-0 items-center border rounded-full transition-colors cursor-pointer",
              draft.enabled ? "bg-primary/25 border-primary/50" : "bg-muted/60 border-border")}
          >
            <span className={cn("inline-block h-3.5 w-3.5 transform rounded-full shadow-sm transition-transform", draft.enabled ? "translate-x-[18px] bg-primary" : "translate-x-[2px] bg-muted-foreground/70")} />
          </button>
          <span className="text-xs text-muted-foreground">Enable this server</span>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" className="cursor-pointer rounded-xl" onClick={onCancel}>Cancel</Button>
          <Button size="sm" className="cursor-pointer rounded-xl" onClick={onSave} disabled={missing || saving}>
            {saving ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : null}
            Save server
          </Button>
        </div>
      </div>
    </Panel>
  );
}

function LimitField({ label, value, fallback, onChange }: { label: string; value: string; fallback: number; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-xs text-muted-foreground font-medium">{label}</Label>
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={`default: ${fallback}`} className="rounded-xl font-mono text-xs" />
    </div>
  );
}
