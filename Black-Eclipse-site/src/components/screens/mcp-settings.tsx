"use client";

// ── Settings › MCP servers (Phase 5E) ─────────────────────────────────────
// Add / test / enable / disable / remove local stdio MCP servers and select
// which of their tools are active. The Python runtime owns the manager and the
// registry; this panel is a thin, secret-free front door.
//
// Honesty rules baked into the UI:
//   • Discovery is not activation — a discovered tool is inert until selected.
//   • Only read-effect tools can be activated in this phase; write / external /
//     unknown tools render clearly disabled with the reason.
//   • A result from an MCP server is external and is NOT Eclipse-verified.
//   • Env VALUES are written but never read back; only key names are shown.

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle, Check, ChevronDown, Loader2, Plug, Plus, RefreshCcw,
  ShieldAlert, Trash2, Unplug, Wrench, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type {
  MCPEffect, MCPTransport, MCPServerView, MCPToolView, MCPSecretView, MCPApprovalView,
  MCPIntegrationView, MCPWorkflowView, MCPDiagnosticView, MCPDiagnosticsResponse,
} from "@/lib/harness/mcp-types";

const EFFECT_LABEL: Record<MCPEffect, string> = {
  read: "Read-only",
  write: "Writes data",
  external_action: "External action",
  unknown: "Unknown effect",
};

const EFFECT_CLASS: Record<MCPEffect, string> = {
  read: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  write: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  external_action: "border-rose-500/30 bg-rose-500/10 text-rose-300",
  unknown: "border-border/40 bg-muted/30 text-muted-foreground",
};

function Panel({ className, children, ...rest }: { className?: string; children: React.ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden", className)} {...rest}>
      {children}
    </div>
  );
}

function EffectBadge({ effect }: { effect: MCPEffect }) {
  return (
    <span className={cn("inline-flex items-center px-1.5 py-0.5 rounded-full text-[9px] font-bold border", EFFECT_CLASS[effect])}>
      {EFFECT_LABEL[effect]}
    </span>
  );
}

function stateDot(state: MCPServerView["state"], enabled: boolean): { ok: boolean; label: string } {
  if (!enabled) return { ok: false, label: "Disabled" };
  if (state === "connected") return { ok: true, label: "Connected" };
  if (state === "failed") return { ok: false, label: "Failed" };
  return { ok: false, label: state };
}

interface DraftServer {
  id: string;
  transport: MCPTransport;
  command: string;
  argsText: string;
  /** HTTP endpoint URL (transport === "http"). */
  url: string;
  /** HTTP auth secret reference (vault secret NAME), e.g. "Authorization Bearer my_token". */
  authKind: "header" | "query";
  authName: string;
  authPrefix: string;
  authSecretRef: string;
  envText: string;
  envAllowlistText: string;
  /** ENV_VAR=secretName per line — vault references, never values. */
  secretRefsText: string;
  cwd: string;
  enabled: boolean;
  selectedTools: string[];
  enabledEffects: MCPEffect[];
  description: string;
  /** Existing env key names (values are never returned to the UI). */
  envKeys: string[];
}

function emptyDraft(): DraftServer {
  return {
    id: "", transport: "stdio", command: "", argsText: "", url: "",
    authKind: "header", authName: "Authorization", authPrefix: "Bearer ", authSecretRef: "",
    envText: "", envAllowlistText: "", secretRefsText: "", cwd: "",
    enabled: false, selectedTools: [], enabledEffects: ["read"], description: "", envKeys: [],
  };
}

/** Parse `ENV_VAR=secretName` per line into a reference map. */
function parseRefs(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    const name = trimmed.slice(eq + 1).trim();
    if (name) out[trimmed.slice(0, eq).trim()] = name;
  }
  return out;
}

/** Parse a KEY=VALUE per line editor into an env map. */
function parseEnv(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    out[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1);
  }
  return out;
}

function ServerEditor({
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
  const toggleTool = (name: string) => {
    setDraft({
      ...draft,
      selectedTools: draft.selectedTools.includes(name)
        ? draft.selectedTools.filter((t) => t !== name)
        : [...draft.selectedTools, name],
    });
  };
  const missing = !draft.id.trim() || (draft.transport === "stdio" ? !draft.command.trim() : !draft.url.trim());
  const isHttp = draft.transport === "http";

  return (
    <Panel className="p-5 space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Server ID</Label>
          <Input
            value={draft.id}
            onChange={(e) => setDraft({ ...draft, id: e.target.value })}
            placeholder="e.g. finance-tools"
            className="rounded-xl font-mono text-xs"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Transport</Label>
          <Select value={draft.transport} onValueChange={(v) => setDraft({ ...draft, transport: (v ?? "stdio") as MCPTransport })}>
            <SelectTrigger className="h-9 rounded-xl text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="stdio">stdio — local subprocess</SelectItem>
              <SelectItem value="http">http — remote Streamable HTTP</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {isHttp ? (
        <>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Endpoint URL</Label>
            <Input
              value={draft.url}
              onChange={(e) => setDraft({ ...draft, url: e.target.value })}
              placeholder="https://mcp.example.com/mcp"
              className="rounded-xl font-mono text-xs"
            />
            <p className="text-[10px] text-muted-foreground/70">Must be https (loopback http is allowed for local testing). Private hosts are refused.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs text-muted-foreground font-medium">Auth kind</Label>
              <Select value={draft.authKind} onValueChange={(v) => setDraft({ ...draft, authKind: (v ?? "header") as "header" | "query" })}>
                <SelectTrigger className="h-9 rounded-xl text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="header">Header</SelectItem>
                  <SelectItem value="query">Query param</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs text-muted-foreground font-medium">Name</Label>
              <Input value={draft.authName} onChange={(e) => setDraft({ ...draft, authName: e.target.value })} placeholder="Authorization" className="rounded-xl font-mono text-xs" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs text-muted-foreground font-medium">Value prefix</Label>
              <Input value={draft.authPrefix} onChange={(e) => setDraft({ ...draft, authPrefix: e.target.value })} placeholder="Bearer " className="rounded-xl font-mono text-xs" />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Vault secret name</Label>
            <Input value={draft.authSecretRef} onChange={(e) => setDraft({ ...draft, authSecretRef: e.target.value })} placeholder="e.g. notion_integration_token" className="rounded-xl font-mono text-xs" />
            <p className="text-[10px] text-muted-foreground/70">The token is stored encrypted in the Secret vault; only its name is kept here.</p>
          </div>
        </>
      ) : (
        <>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Command</Label>
            <Input
              value={draft.command}
              onChange={(e) => setDraft({ ...draft, command: e.target.value })}
              placeholder="e.g. npx or python"
              className="rounded-xl font-mono text-xs"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Arguments (one per line)</Label>
            <textarea
              value={draft.argsText}
              onChange={(e) => setDraft({ ...draft, argsText: e.target.value })}
              rows={3}
              placeholder={"-y\n@modelcontextprotocol/server-filesystem\n/path/to/dir"}
              className="rounded-xl border border-border/40 bg-background/60 px-3 py-2 text-xs font-mono text-foreground outline-none focus:border-primary/40"
            />
            <p className="text-[10px] text-muted-foreground/70">
              Passed as an argv list — never through a shell.
            </p>
          </div>
        </>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Environment (KEY=VALUE per line)</Label>
          <textarea
            value={draft.envText}
            onChange={(e) => setDraft({ ...draft, envText: e.target.value })}
            rows={3}
            placeholder={draft.envKeys.length ? `${draft.envKeys[0]}=` : "API_BASE_URL=https://…"}
            className="rounded-xl border border-border/40 bg-background/60 px-3 py-2 text-xs font-mono text-foreground outline-none focus:border-primary/40"
          />
          <p className="text-[10px] text-muted-foreground/70">
            Scoped to this server only. Leave the value blank (<span className="font-mono">KEY=</span>) to keep the
            stored secret. Values are stored locally and never shown again.
            {draft.envKeys.length > 0 && (
              <> Stored keys: <span className="font-mono">{draft.envKeys.join(", ")}</span>.</>
            )}
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Host env vars to pass through (optional)</Label>
          <Input
            value={draft.envAllowlistText}
            onChange={(e) => setDraft({ ...draft, envAllowlistText: e.target.value })}
            placeholder="e.g. FOO BAR"
            className="rounded-xl font-mono text-xs"
          />
          <p className="text-[10px] text-muted-foreground/70">
            Names copied from the host environment into the server. Nothing else is forwarded.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label className="text-xs text-muted-foreground font-medium">Vault secret references (ENV_VAR=secretName per line)</Label>
        <textarea
          value={draft.secretRefsText}
          onChange={(e) => setDraft({ ...draft, secretRefsText: e.target.value })}
          rows={2}
          placeholder="API_TOKEN=my_server_token"
          className="rounded-xl border border-border/40 bg-background/60 px-3 py-2 text-xs font-mono text-foreground outline-none focus:border-primary/40"
        />
        <p className="text-[10px] text-muted-foreground/70">
          Preferred over an inline value: the secret is stored encrypted in the vault and resolved at spawn. Add
          secrets in the Vault panel below.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label className="text-xs text-muted-foreground font-medium">Effects allowed for this server</Label>
        <div className="flex items-center gap-4 flex-wrap">
          {(["read", "write", "external_action"] as MCPEffect[]).map((eff) => (
            <label key={eff} className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
              <input
                type="checkbox"
                className="accent-primary"
                checked={draft.enabledEffects.includes(eff)}
                disabled={eff === "read"}
                onChange={() =>
                  setDraft({
                    ...draft,
                    enabledEffects: draft.enabledEffects.includes(eff)
                      ? draft.enabledEffects.filter((e) => e !== eff)
                      : [...draft.enabledEffects, eff],
                  })
                }
              />
              <EffectBadge effect={eff} />
            </label>
          ))}
        </div>
        <p className="text-[10px] text-muted-foreground/70">
          Write/action tools additionally require a per-call approval bound to the exact arguments before they run.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label className="text-xs text-muted-foreground font-medium">Working directory (optional)</Label>
        <Input
          value={draft.cwd}
          onChange={(e) => setDraft({ ...draft, cwd: e.target.value })}
          placeholder="relative to the app root"
          className="rounded-xl font-mono text-xs"
        />
        <p className="text-[10px] text-muted-foreground/70">
          A relative path resolves against the app root, not the launch directory.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={onTest} disabled={missing || testing}>
          {testing ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Plug className="w-3.5 h-3.5 mr-1" />}
          Test connection
        </Button>
        {testResult && (
          <span className={cn("text-[11px] flex items-center gap-1", testResult.state === "connected" ? "text-emerald-400" : "text-rose-400")}>
            {testResult.state === "connected" ? <Check className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
            {testResult.state === "connected" ? `Connected · ${testResult.tools.length} tool(s) discovered` : testResult.diagnostic || "Connection failed"}
          </span>
        )}
      </div>

      {testResult && testResult.tools.length > 0 && (
        <div className="rounded-xl border border-border/20 glass-card-subtle">
          <div className="px-4 py-2.5 border-b border-border/10 flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Discovered tools</span>
            <span className="text-[10px] text-muted-foreground">Select the read-only tools to enable</span>
          </div>
          <div className="divide-y divide-border/10 max-h-64 overflow-y-auto">
            {testResult.tools.map((tool) => {
              const activatable = tool.effect === "read" && !tool.diagnostic;
              const checked = draft.selectedTools.includes(tool.originalName);
              return (
                <label
                  key={tool.originalName}
                  className={cn(
                    "flex items-start gap-3 px-4 py-2.5",
                    activatable ? "cursor-pointer hover:bg-accent/20" : "opacity-60"
                  )}
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 accent-primary"
                    checked={checked}
                    disabled={!activatable}
                    onChange={() => activatable && toggleTool(tool.originalName)}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-mono text-foreground">{tool.originalName}</span>
                      <EffectBadge effect={tool.effect} />
                      {tool.diagnostic && <span className="text-[10px] text-rose-400">{tool.diagnostic}</span>}
                    </div>
                    {tool.description && <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">{tool.description}</p>}
                  </div>
                </label>
              );
            })}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-3 pt-1">
        <div className="flex items-center gap-2">
          <button
            role="switch"
            aria-checked={draft.enabled}
            onClick={() => setDraft({ ...draft, enabled: !draft.enabled })}
            className={cn(
              "relative inline-flex h-5 w-9 shrink-0 items-center border rounded-full transition-colors cursor-pointer",
              draft.enabled ? "bg-primary/25 border-primary/50" : "bg-muted/60 border-border"
            )}
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

function ServerCard({
  server,
  onToggleEnabled,
  onSelectTool,
  onRemove,
  onEdit,
  onConfirmCatalog,
  busy,
}: {
  server: MCPServerView;
  onToggleEnabled: () => void;
  onSelectTool: (tool: string, selected: boolean) => void;
  onRemove: () => void;
  onEdit: () => void;
  onConfirmCatalog: () => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const dot = stateDot(server.state, server.enabled);
  // A discovered catalog whose digest differs from the operator's last reviewed
  // digest must be re-confirmed before an annotation-sourced read tool can run.
  const catalogChanged =
    server.enabled && server.state === "connected" && !!server.catalogDigest &&
    server.catalogDigest !== server.confirmedCatalogDigest;
  return (
    <Panel>
      <div className="flex items-center gap-3 px-5 py-3.5">
        <span className={cn("w-2 h-2 rounded-full shrink-0", dot.ok ? "bg-emerald-400 shadow-[0_0_8px] shadow-emerald-400/60" : "bg-muted-foreground/40")} />
        <button className="flex items-center gap-2 min-w-0 flex-1 text-left cursor-pointer" onClick={() => setOpen((o) => !o)}>
          <span className="text-xs font-semibold text-foreground truncate">{server.name || server.id}</span>
          <span className="text-[10px] font-mono text-muted-foreground truncate">{server.transport === "http" ? server.url : server.command}</span>
          <span className="text-[10px] text-muted-foreground font-mono">{dot.label}</span>
          {server.secretCount > 0 && <span className="text-[10px] text-muted-foreground font-mono">· {server.secretCount} secret(s)</span>}
          <ChevronDown className={cn("w-3.5 h-3.5 text-muted-foreground transition-transform", open && "rotate-180")} />
        </button>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            role="switch"
            aria-checked={server.enabled}
            onClick={onToggleEnabled}
            disabled={busy}
            title={server.enabled ? "Disable" : "Enable"}
            className={cn(
              "relative inline-flex h-5 w-9 shrink-0 items-center border rounded-full transition-colors cursor-pointer",
              server.enabled ? "bg-primary/25 border-primary/50" : "bg-muted/60 border-border"
            )}
          >
            <span className={cn("inline-block h-3.5 w-3.5 transform rounded-full shadow-sm transition-transform", server.enabled ? "translate-x-[18px] bg-primary" : "translate-x-[2px] bg-muted-foreground/70")} />
          </button>
          <Button variant="ghost" size="sm" className="cursor-pointer rounded-xl" onClick={onEdit} disabled={busy}>
            <Wrench className="w-3.5 h-3.5" />
          </Button>
          <Button variant="ghost" size="sm" className="cursor-pointer rounded-xl text-rose-400 hover:text-rose-300" onClick={onRemove} disabled={busy}>
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {open && (
        <div className="px-5 pb-4 space-y-3 border-t border-border/10 pt-3">
          {server.diagnostic && (
            <div className="flex items-start gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2">
              <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-[11px] text-muted-foreground">{server.diagnostic}</p>
            </div>
          )}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] text-muted-foreground font-mono">
            <span>protocol: {server.protocolVersion || "—"}</span>
            <span>server: {server.serverInfo?.name || "—"}</span>
            <span>catalog: {server.catalogDigest || "—"}</span>
            <span>registered: {server.registeredTools.length}</span>
          </div>
          {catalogChanged && (
            <div className="flex items-start justify-between gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2">
              <div className="flex items-start gap-2">
                <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                <p className="text-[11px] text-muted-foreground">
                  This server&apos;s tool catalog changed since you last reviewed it
                  {server.confirmedCatalogDigest ? "" : " (it has never been confirmed)"}. Tools advertised as
                  read-only by the server stay disabled until you review and confirm the catalog.
                </p>
              </div>
              <Button size="sm" variant="outline" className="cursor-pointer rounded-xl shrink-0" onClick={onConfirmCatalog} disabled={busy}>
                Confirm catalog
              </Button>
            </div>
          )}
          {server.args.length > 0 && (
            <p className="text-[10px] font-mono text-muted-foreground break-all">args: {server.args.join(" ")}</p>
          )}
          {server.envKeys.length > 0 && (
            <p className="text-[10px] font-mono text-muted-foreground">env keys: {server.envKeys.join(", ")}</p>
          )}
          <div className="rounded-xl border border-border/20 glass-card-subtle">
            <div className="px-4 py-2 border-b border-border/10 text-[10px] uppercase tracking-widest font-bold text-muted-foreground">
              Tools ({server.tools.length} discovered)
            </div>
            {server.tools.length === 0 ? (
              <p className="px-4 py-4 text-[11px] text-muted-foreground text-center">
                {server.enabled ? "No tools discovered (the server may have failed — see the diagnostic above)." : "Enable the server to discover its tools."}
              </p>
            ) : (
              <div className="divide-y divide-border/10">
                {server.tools.map((tool) => {
                  const activatable = tool.effect === "read" && !tool.diagnostic;
                  const selected = server.selectedTools.includes(tool.originalName);
                  return (
                    <label key={tool.originalName} className={cn("flex items-start gap-3 px-4 py-2.5", activatable ? "cursor-pointer hover:bg-accent/20" : "opacity-70")}>
                      <input
                        type="checkbox"
                        className="mt-0.5 accent-primary"
                        checked={selected}
                        disabled={!activatable || busy}
                        onChange={(e) => activatable && onSelectTool(tool.originalName, e.target.checked)}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-mono text-foreground">{tool.originalName}</span>
                          <EffectBadge effect={tool.effect} />
                          <span className="text-[9px] font-mono text-muted-foreground">→ {tool.eclipseName}</span>
                          {selected && activatable && <span className="text-[9px] text-primary">active</span>}
                        </div>
                        {tool.description && <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">{tool.description}</p>}
                        {!activatable && !tool.diagnostic && (
                          <p className="text-[10px] text-muted-foreground/70 mt-0.5">
                            Only read-only tools can be enabled in this phase.
                          </p>
                        )}
                        {tool.diagnostic && <p className="text-[10px] text-rose-400 mt-0.5">{tool.diagnostic}</p>}
                      </div>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}

export function MCPSettingsPanel() {
  const [servers, setServers] = useState<MCPServerView[]>([]);
  const [summary, setSummary] = useState({ configured: 0, connected: 0, registeredTools: 0 });
  const [loadDiagnostics, setLoadDiagnostics] = useState<Array<{ server: string; code: string; message: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<DraftServer | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ state: string; diagnostic?: string | null; tools: MCPToolView[] } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/harness/mcp/servers");
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Failed to load MCP servers");
        return;
      }
      setServers(body.servers ?? []);
      setSummary({ configured: body.configured ?? 0, connected: body.connected ?? 0, registeredTools: body.registeredTools ?? 0 });
      setLoadDiagnostics(body.loadDiagnostics ?? []);
    } catch {
      setError("Failed to reach the MCP catalog endpoint");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const draftToPayload = (d: DraftServer) => {
    const parsed = parseEnv(d.envText);
    // A blank value ("KEY=") means "keep the stored value": it is listed as a key
    // to retain but omitted from `env`, so the runtime preserves the secret. A
    // non-empty value overwrites.
    const env: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (value !== "") env[key] = value;
    }
    const envKeys = Object.keys(parsed);
    const allowlist = d.envAllowlistText.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);
    const isHttp = d.transport === "http";
    const auth = isHttp && d.authSecretRef.trim()
      ? { kind: d.authKind, name: d.authName.trim() || "Authorization", prefix: d.authPrefix || undefined, secretRef: d.authSecretRef.trim() }
      : undefined;
    return {
      server: {
        id: d.id.trim(),
        transport: d.transport,
        command: isHttp ? undefined : d.command.trim(),
        args: isHttp ? [] : d.argsText.split(/\r?\n/).map((a) => a.trim()).filter(Boolean),
        url: isHttp ? d.url.trim() : undefined,
        auth,
        env,
        envAllowlist: allowlist,
        secretRefs: parseRefs(d.secretRefsText),
        cwd: d.cwd.trim() || undefined,
        enabled: d.enabled,
        selectedTools: d.selectedTools,
        enabledEffects: d.enabledEffects.length ? d.enabledEffects : ["read"],
        description: d.description.trim() || undefined,
      },
      envKeys,
    };
  };

  const saveDraft = async () => {
    if (!editing) return;
    setSaving(true);
    setError(null);
    try {
      const payload = draftToPayload(editing);
      const res = await fetch("/api/harness/mcp/servers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Save failed");
      setEditing(null);
      setTestResult(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const testDraft = async () => {
    if (!editing) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch("/api/harness/mcp/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ server: draftToPayload(editing).server }),
      });
      const body = await res.json();
      setTestResult({ state: body.state ?? "failed", diagnostic: body.diagnostic, tools: body.tools ?? [] });
    } catch {
      setTestResult({ state: "failed", diagnostic: "Test request failed", tools: [] });
    } finally {
      setTesting(false);
    }
  };

  const updateServer = async (server: MCPServerView, patch: { enabled?: boolean; selectedTools?: string[] }) => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/harness/mcp/servers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          server: {
            id: server.id,
            name: server.name ?? undefined,
            transport: server.transport,
            command: server.command,
            args: server.args,
            url: server.url ?? undefined,
            auth: server.auth ?? undefined,
            envAllowlist: server.envAllowlist,
            secretRefs: server.secretRefs,
            cwd: server.cwd ?? undefined,
            enabled: patch.enabled ?? server.enabled,
            // No `env` is sent, so the runtime merges and preserves existing
            // scoped values. Budgets are carried so a toggle cannot reset them.
            ...(server.limits ?? {}),
            selectedTools: patch.selectedTools ?? server.selectedTools,
            toolEffects: server.toolEffects,
            enabledEffects: server.enabledEffects,
            description: server.description ?? undefined,
          },
        }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Update failed");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setBusy(false);
    }
  };

  const confirmCatalog = async (server: MCPServerView) => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/harness/mcp/servers/${encodeURIComponent(server.id)}/confirm`, { method: "POST" });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Confirm failed");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirm failed");
    } finally {
      setBusy(false);
    }
  };

  const removeServer = async (server: MCPServerView) => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/harness/mcp/servers/${encodeURIComponent(server.id)}`, { method: "DELETE" });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Remove failed");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Remove failed");
    } finally {
      setBusy(false);
    }
  };

  const editServer = (server: MCPServerView) => {
    setTestResult(null);
    setEditing({
      id: server.id,
      transport: server.transport ?? "stdio",
      command: server.command,
      argsText: server.args.join("\n"),
      url: server.url ?? "",
      authKind: (server.auth?.kind ?? "header") as "header" | "query",
      authName: server.auth?.name ?? "Authorization",
      authPrefix: server.auth?.prefix ?? "Bearer ",
      authSecretRef: server.auth?.secretRef ?? "",
      // Seed one blank line per stored key so a save keeps them unless removed.
      envText: server.envKeys.map((k) => `${k}=`).join("\n"),
      envAllowlistText: server.envAllowlist.join(" "),
      secretRefsText: Object.entries(server.secretRefs ?? {}).map(([envName, secretName]) => `${envName}=${secretName}`).join("\n"),
      cwd: server.cwd ?? "",
      enabled: server.enabled,
      selectedTools: server.selectedTools,
      enabledEffects: server.enabledEffects?.length ? server.enabledEffects : ["read"],
      description: server.description ?? "",
      envKeys: server.envKeys,
    });
  };

  return (
    <div className="animate-fade-in-up">
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
            <Plug className="text-primary" size={22} />
          </span>
          <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">MCP Servers</h2>
        </div>
        <p className="text-xs text-muted-foreground mt-2 leading-relaxed max-w-lg">
          Connect MCP servers and choose which of their tools the agent may use. Start from a{" "}
          <strong>finance workflow</strong> below, or add a server directly. Discovered tools are inert until you
          select them; write/action tools need a per-call approval. Results from a server are attributed to it and
          are <strong>never</strong> Eclipse-verified.
        </p>
      </div>

      <FinanceWorkflowWizard
        busy={busy}
        onAddServer={(draft) => { setTestResult(null); setEditing(draft); }}
      />
      <MCPDiagnosticsPanel busy={busy} />

      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground font-mono">
          <span>{summary.configured} configured</span>
          <span>·</span>
          <span>{summary.connected} connected</span>
          <span>·</span>
          <span>{summary.registeredTools} tool(s) active</span>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={() => void load()} disabled={loading || busy}>
            <RefreshCcw className={cn("w-3.5 h-3.5 mr-1", loading && "animate-spin")} /> Refresh
          </Button>
          <Button
            size="sm"
            className="cursor-pointer rounded-xl"
            onClick={() => { setTestResult(null); setEditing(emptyDraft()); }}
            disabled={busy}
          >
            <Plus className="w-3.5 h-3.5 mr-1" /> Add server
          </Button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-500/20 bg-rose-500/5 px-4 py-3 mb-4">
          <ShieldAlert className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-0.5" />
          <p className="text-[11px] text-muted-foreground">{error}</p>
        </div>
      )}

      {loadDiagnostics.length > 0 && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 mb-4">
          <p className="text-[11px] text-muted-foreground">
            {loadDiagnostics.length} config entr{loadDiagnostics.length === 1 ? "y" : "ies"} could not be loaded:
            {" "}{loadDiagnostics.map((d) => `${d.server} (${d.code})`).join(", ")}
          </p>
        </div>
      )}

      {editing && (
        <div className="mb-4">
          <ServerEditor
            draft={editing}
            setDraft={setEditing}
            onCancel={() => { setEditing(null); setTestResult(null); }}
            onSave={saveDraft}
            onTest={testDraft}
            saving={saving}
            testing={testing}
            testResult={testResult}
          />
        </div>
      )}

      {loading && servers.length === 0 ? (
        <Panel className="p-8 flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin text-primary" />
          <span className="text-xs text-muted-foreground">Loading MCP servers…</span>
        </Panel>
      ) : servers.length === 0 && !editing ? (
        <Panel className="p-8 text-center">
          <Unplug className="mx-auto text-muted-foreground w-8 h-8 mb-3" />
          <p className="text-xs text-muted-foreground max-w-md mx-auto">
            No MCP servers configured. Add a local server to give the agent new tools. Servers run as
            subprocesses and receive only the environment you scope to them.
          </p>
        </Panel>
      ) : (
        <div className="space-y-3">
          {servers.map((server) => (
            <ServerCard
              key={server.id}
              server={server}
              busy={busy}
              onToggleEnabled={() => void updateServer(server, { enabled: !server.enabled })}
              onSelectTool={(tool, selected) => {
                const next = selected
                  ? [...server.selectedTools, tool]
                  : server.selectedTools.filter((t) => t !== tool);
                void updateServer(server, { selectedTools: next });
              }}
              onRemove={() => void removeServer(server)}
              onEdit={() => editServer(server)}
              onConfirmCatalog={() => void confirmCatalog(server)}
            />
          ))}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 mt-5">
        <MCPSecretsPanel busy={busy} onError={setError} />
        <MCPApprovalsPanel busy={busy} onError={setError} />
      </div>

      <p className="text-[10px] text-muted-foreground/60 mt-4 leading-relaxed">
        <X className="inline w-3 h-3 -mt-0.5" /> Remote HTTP/OAuth servers, Eclipse acting as an MCP server, and
        resources/prompts/subscriptions are future work. Local stdio servers, vault-backed secret references, and
        per-call effectful-tool approvals are implemented.
      </p>
    </div>
  );
}

// ── Vault secrets panel ─────────────────────────────────────────────────────

function MCPSecretsPanel({ busy, onError }: { busy: boolean; onError: (m: string) => void }) {
  const [secrets, setSecrets] = useState<MCPSecretView[]>([]);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [working, setWorking] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/harness/mcp/secrets");
      const body = await res.json();
      if (res.ok) setSecrets(body.secrets ?? []);
    } catch {
      /* non-fatal */
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const save = async () => {
    if (!name.trim() || !value.trim()) return;
    setWorking(true);
    try {
      const res = await fetch("/api/harness/mcp/secrets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), value }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Save failed");
      setName("");
      setValue("");
      await load();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Secret save failed");
    } finally {
      setWorking(false);
    }
  };

  const remove = async (secretName: string) => {
    setWorking(true);
    try {
      await fetch(`/api/harness/mcp/secrets?name=${encodeURIComponent(secretName)}`, { method: "DELETE" });
      await load();
    } finally {
      setWorking(false);
    }
  };

  return (
    <Panel className="p-5">
      <div className="flex items-center gap-2 mb-2">
        <ShieldAlert className="w-4 h-4 text-primary" />
        <h3 className="text-sm font-semibold text-foreground">Secret vault</h3>
      </div>
      <p className="text-[10px] text-muted-foreground mb-3 leading-relaxed">
        Named secrets, encrypted at rest. A server references a name — the value never reaches a browser, the model,
        a log, or a run trace.
      </p>
      <div className="flex flex-col gap-2 mb-3">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="secret name (e.g. my_server_token)" className="rounded-xl font-mono text-xs" />
        <Input type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="secret value" className="rounded-xl font-mono text-xs" />
        <Button size="sm" className="cursor-pointer rounded-xl self-start" onClick={() => void save()} disabled={working || busy || !name.trim() || !value.trim()}>
          {working ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : null} Store secret
        </Button>
      </div>
      {secrets.length === 0 ? (
        <p className="text-[11px] text-muted-foreground/70">No secrets stored.</p>
      ) : (
        <div className="divide-y divide-border/10">
          {secrets.map((s) => (
            <div key={s.name} className="flex items-center justify-between gap-2 py-2">
              <span className="text-xs font-mono text-foreground truncate">{s.name}</span>
              <span className="text-[10px] font-mono text-muted-foreground">{s.hint ?? "configured"}</span>
              <Button variant="ghost" size="sm" className="cursor-pointer rounded-xl text-rose-400" onClick={() => void remove(s.name)} disabled={working}>
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

// ── Approvals panel (5G) ────────────────────────────────────────────────────

function MCPApprovalsPanel({ busy, onError }: { busy: boolean; onError: (m: string) => void }) {
  const [approvals, setApprovals] = useState<MCPApprovalView[]>([]);
  const [working, setWorking] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/harness/mcp/approvals?status=pending");
      const body = await res.json();
      if (res.ok) setApprovals(body.approvals ?? []);
    } catch {
      /* non-fatal */
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const decide = async (id: string, approve: boolean) => {
    setWorking(true);
    try {
      const res = await fetch(`/api/harness/mcp/approvals/${encodeURIComponent(id)}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approve }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Decision failed");
      await load();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Decision failed");
    } finally {
      setWorking(false);
    }
  };

  return (
    <Panel className="p-5">
      <div className="flex items-center gap-2 mb-2">
        <Wrench className="w-4 h-4 text-primary" />
        <h3 className="text-sm font-semibold text-foreground">Pending approvals</h3>
      </div>
      <p className="text-[10px] text-muted-foreground mb-3 leading-relaxed">
        A write/action MCP tool is blocked until you approve the exact call. The approval is bound to the server,
        tool, and argument digest, and expires.
      </p>
      {approvals.length === 0 ? (
        <p className="text-[11px] text-muted-foreground/70">No pending approvals.</p>
      ) : (
        <div className="space-y-2">
          {approvals.map((a) => (
            <div key={a.id} className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-mono text-foreground">{a.tool}</span>
                <EffectBadge effect={a.effect} />
                {a.risk && (
                  <span className={cn("text-[9px] font-bold uppercase", a.risk === "high" ? "text-rose-400" : "text-muted-foreground")}>
                    {a.risk} risk
                  </span>
                )}
                <span className="text-[9px] font-mono text-muted-foreground">{a.serverId}</span>
              </div>
              {a.actionSummary && <p className="text-[11px] text-foreground/90 mt-1">{a.actionSummary}</p>}
              {a.affectedData && (
                <p className="text-[9px] font-mono text-muted-foreground mt-1 break-all">affects: {a.affectedData}</p>
              )}
              <p className="text-[9px] font-mono text-muted-foreground mt-1 break-all">digest {a.argsDigest.slice(0, 16)}…</p>
              <div className="flex items-center gap-2 mt-2">
                <Button size="sm" className="cursor-pointer rounded-xl" onClick={() => void decide(a.id, true)} disabled={working || busy}>Approve this exact call</Button>
                <Button size="sm" variant="ghost" className="cursor-pointer rounded-xl text-rose-400" onClick={() => void decide(a.id, false)} disabled={working || busy}>Deny</Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

// -- Finance workflow wizard (task-oriented setup) ---------------------------

function FinanceWorkflowWizard({
  busy,
  onAddServer,
}: {
  busy: boolean;
  onAddServer: (draft: DraftServer) => void;
}) {
  const [workflows, setWorkflows] = useState<MCPWorkflowView[]>([]);
  const [integrations, setIntegrations] = useState<MCPIntegrationView[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/harness/mcp/meta");
        const body = await res.json();
        if (res.ok) {
          setWorkflows(body.workflows ?? []);
          setIntegrations(body.integrations ?? []);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const byId = new Map(integrations.map((i) => [i.id, i]));
  const active = workflows.find((w) => w.id === selected) ?? null;

  const draftFromIntegration = (integrationId: string): DraftServer => {
    const spec = byId.get(integrationId);
    const base = emptyDraft();
    if (!spec) return base;
    return {
      ...base,
      id: spec.id,
      transport: spec.transport,
      command: spec.command ?? "",
      argsText: (spec.args ?? []).join("\n"),
      url: spec.url ?? "",
      authSecretRef: spec.secret_ref ?? "",
      enabled: true,
      enabledEffects: ["read"],
      description: spec.purpose,
    };
  };

  return (
    <Panel className="p-5 mb-4">
      <div className="flex items-center gap-2 mb-2">
        <Wrench className="w-4 h-4 text-primary" />
        <h3 className="text-sm font-semibold text-foreground">Start from a finance workflow</h3>
      </div>
      <p className="text-[10px] text-muted-foreground mb-3 leading-relaxed">
        Pick the job you want to do. Eclipse shows which integrations it needs and what each step does � nothing is
        enabled until you review and activate it.
      </p>
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading workflows�</div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2 mb-3">
            {workflows.map((w) => (
              <button
                key={w.id}
                onClick={() => setSelected(w.id === selected ? null : w.id)}
                title={w.requiresProvisioning ? w.provisioningNote : undefined}
                className={cn(
                  "rounded-xl border px-3 py-1.5 text-[11px] transition-colors cursor-pointer",
                  w.id === selected ? "border-primary/50 bg-primary/15 text-primary" : "border-border/30 text-muted-foreground hover:bg-accent/20",
                  w.requiresProvisioning && "opacity-70"
                )}
              >
                {w.name}
                {w.requiresProvisioning && <span className="ml-1 text-[9px] text-amber-400">unavailable</span>}
              </button>
            ))}
          </div>
          {active && (
            <div className="rounded-xl border border-border/20 glass-card-subtle p-4 space-y-3">
              <div>
                <p className="text-xs text-foreground">{active.summary}</p>
                <p className="text-[10px] text-muted-foreground mt-1">Produces: {active.output}</p>
              </div>
              {active.requiresProvisioning && (
                <div className="flex items-start gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2">
                  <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                  <p className="text-[11px] text-muted-foreground">
                    <strong className="text-foreground/90">Not available yet.</strong> {active.provisioningNote}
                  </p>
                </div>
              )}
              <div>
                <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-1">Steps</p>
                <ol className="space-y-1">
                  {active.steps.map((s) => (
                    <li key={s.id} className="flex items-start gap-2 text-[11px]">
                      <span className="text-muted-foreground font-mono">{s.effect === "read" ? "�" : "?"}</span>
                      <span className={cn(s.effect === "read" ? "text-muted-foreground" : "text-amber-300")}>
                        <strong className="text-foreground/90">{s.title}</strong> � {s.detail}
                        {s.native_data && <em className="text-[10px]"> (Eclipse data)</em>}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
              {active.integrations.length > 0 && (
                <div>
                  <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-1">Integrations needed</p>
                  <div className="flex flex-wrap gap-2">
                    {active.integrations.map((id) => {
                      const spec = byId.get(id);
                      if (!spec) return null;
                      return (
                        <div key={id} className="rounded-xl border border-border/30 px-3 py-2">
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] text-foreground">{spec.label}</span>
                            {!spec.verified && <span className="text-[9px] text-amber-300">unverified</span>}
                            {spec.verified && spec.community && <span className="text-[9px] text-muted-foreground">community</span>}
                          </div>
                          <p className="text-[10px] text-muted-foreground mt-0.5 max-w-xs">{spec.purpose}</p>
                          {spec.secret_label && <p className="text-[9px] text-muted-foreground/80 mt-0.5">Needs: {spec.secret_label}</p>}
                          <Button
                            size="sm" variant="outline" className="mt-1.5 h-6 cursor-pointer rounded-lg text-[10px]"
                            disabled={busy}
                            onClick={() => onAddServer(draftFromIntegration(id))}
                          >
                            Set up {spec.label}
                          </Button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

// -- Setup diagnostics -------------------------------------------------------

const DIAG_STYLE: Record<string, string> = {
  ok: "text-emerald-400",
  warn: "text-amber-400",
  error: "text-rose-400",
  skipped: "text-muted-foreground",
};

function MCPDiagnosticsPanel({ busy }: { busy: boolean }) {
  const [data, setData] = useState<MCPDiagnosticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/harness/mcp/diagnostics");
      const body = await res.json();
      if (res.ok) setData(body);
    } catch {
      /* non-fatal */
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const errors = data ? [...data.environment, ...data.servers.flatMap((s) => s.checks)].filter((c) => c.status === "error").length : 0;

  return (
    <Panel className="p-5 mb-4">
      <button className="flex w-full items-center justify-between cursor-pointer" onClick={() => setOpen((o) => !o)}>
        <div className="flex items-center gap-2">
          {errors > 0 ? <ShieldAlert className="w-4 h-4 text-rose-400" /> : <Check className="w-4 h-4 text-emerald-400" />}
          <h3 className="text-sm font-semibold text-foreground">Setup diagnostics</h3>
          {data && <span className="text-[10px] text-muted-foreground">{errors} issue(s)</span>}
        </div>
        <ChevronDown className={cn("w-4 h-4 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          <Button size="sm" variant="outline" className="cursor-pointer rounded-xl" onClick={() => void load()} disabled={loading || busy}>
            <RefreshCcw className={cn("w-3.5 h-3.5 mr-1", loading && "animate-spin")} /> Re-check
          </Button>
          {!data ? (
            <p className="text-[11px] text-muted-foreground">No diagnostics yet.</p>
          ) : (
            <>
              <DiagGroup title="Environment" checks={data.environment} />
              {data.servers.map((s) => (
                <DiagGroup key={s.serverId} title={`${s.serverId} (${s.transport})`} checks={s.checks} />
              ))}
            </>
          )}
        </div>
      )}
    </Panel>
  );
}

function DiagGroup({ title, checks }: { title: string; checks: MCPDiagnosticView[] }) {
  if (!checks.length) return null;
  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-1">{title}</p>
      <div className="space-y-1">
        {checks.map((c) => (
          <div key={`${title}:${c.code}`} className="flex items-start gap-2 text-[11px]">
            <span className={cn("font-mono", DIAG_STYLE[c.status] ?? "text-muted-foreground")}>{c.status}</span>
            <span className="text-muted-foreground">
              {c.message}
              {c.status !== "ok" && c.recovery && <span className="block text-[10px] text-foreground/70">{c.recovery}</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}