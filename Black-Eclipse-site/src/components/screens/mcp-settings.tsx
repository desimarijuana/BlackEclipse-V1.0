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
  ShieldAlert, Trash2, Unplug, Wrench,
} from "@/lib/icons";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type {
  MCPServerView, MCPToolView, MCPSecretView,
  MCPIntegrationView, MCPWorkflowView, MCPDiagnosticView, MCPDiagnosticsResponse,
  MCPSupplyChainReport, MCPVerifyResult,
} from "@/lib/harness/mcp-types";
import {
  catalogChangeSummary, draftFromServer, draftToInput, emptyDraft, selectedToolNames,
  resolveSelectedByGlobs, type DraftServer,
} from "@/lib/harness/mcp-draft";
import { Panel, EffectBadge, stateDot, StateDot } from "./mcp/primitives";
import { ServerEditor } from "./mcp/server-editor";
import { MCPLifecyclePanel } from "./mcp/lifecycle-panel";
import { CredentialsPanel } from "./mcp/credentials-panel";
import { MCPApprovalsPanel } from "./mcp/approvals-panel";

function ServerCard({
  server,
  onToggleEnabled,
  onSelectTool,
  onRemove,
  onEdit,
  onConfirmCatalog,
  onOauthLogin,
  onOauthLogout,
  onVerify,
  onResetCircuit,
  busy,
}: {
  server: MCPServerView;
  onToggleEnabled: () => void;
  onSelectTool: (tool: string, selected: boolean) => void;
  onRemove: () => void;
  onEdit: () => void;
  onConfirmCatalog: () => void;
  onOauthLogin: () => Promise<{ verificationUri?: string; userCode?: string }>;
  onOauthLogout: () => void;
  onVerify: (tool: string, args: Record<string, unknown>) => Promise<MCPVerifyResult | { error: string }>;
  onResetCircuit: () => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const dot = stateDot(server.state, server.enabled);
  const [oauthState, setOauthState] = useState<{ verificationUri?: string; userCode?: string } | null>(null);
  // A discovered catalog whose digest differs from the operator's last reviewed
  // digest must be re-confirmed before an annotation-sourced read tool can run.
  const catalogChanged =
    server.enabled && server.state === "connected" && !!server.catalogDigest &&
    server.catalogDigest !== server.confirmedCatalogDigest;
  const isOauth = server.auth?.kind === "oauth";
  return (
    <Panel>
      <div className="flex items-center gap-3 px-5 py-3.5">
        <StateDot tone={dot.tone} />
        <button className="flex items-center gap-2 min-w-0 flex-1 text-left cursor-pointer" onClick={() => setOpen((o) => !o)}>
          <span className="text-xs font-semibold text-foreground truncate">{server.name || server.id}</span>
          <span className="text-[10px] font-mono text-muted-foreground truncate">
            {server.transport === "stdio" ? server.command : server.url}
          </span>
          <span className="text-[10px] text-muted-foreground font-mono">{dot.label}</span>
          {server.untrusted && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full border border-rose-500/40 bg-rose-500/15 text-rose-300">UNTRUSTED</span>}
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
          {server.untrusted && (
            <div className="flex items-start gap-2 rounded-xl border border-rose-500/20 bg-rose-500/5 px-3 py-2">
              <ShieldAlert className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-0.5" />
              <p className="text-[11px] text-muted-foreground">
                <strong className="text-rose-300">Untrusted server.</strong> Every non-read call needs a per-call
                approval regardless of the enabled effects, and this server&apos;s own annotations can never activate a tool.
              </p>
            </div>
          )}
          {server.diagnostic && (
            <div className="flex items-start gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2">
              <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-[11px] text-muted-foreground">{server.diagnostic}</p>
            </div>
          )}
          {lifecycleSummary(server)}
          <MCPLifecyclePanel server={server} busy={busy} onResetCircuit={onResetCircuit} />
          {isOauth && (
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border/20 glass-card-subtle px-3 py-2">
              <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">OAuth</span>
              <Button size="sm" variant="outline" className="cursor-pointer rounded-xl" disabled={busy}
                onClick={async () => setOauthState(await onOauthLogin())}>
                Sign in
              </Button>
              <Button size="sm" variant="ghost" className="cursor-pointer rounded-xl text-rose-400" disabled={busy} onClick={onOauthLogout}>
                Sign out
              </Button>
              {oauthState?.userCode && (
                <span className="text-[11px] text-muted-foreground">
                  Go to <span className="font-mono text-foreground">{oauthState.verificationUri}</span> and enter code{" "}
                  <span className="font-mono text-foreground">{oauthState.userCode}</span>.
                </span>
              )}
            </div>
          )}
          <CredentialsPanel server={server} busy={busy} onVerify={onVerify} />
          {server.capabilities && (
            <div className="text-[10px] text-muted-foreground font-mono">
              advertised: {Object.entries(server.capabilities).filter(([, v]) => v).map(([k]) => k).join(", ") || "none"}
              {" · "}
              enabled here: {Object.entries(server.capabilityToggles ?? {}).filter(([, v]) => v).map(([k]) => k).join(", ") || "none"}
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
                <div className="space-y-0.5">
                  <p className="text-[11px] text-muted-foreground">
                    This server&apos;s tool catalog changed since you last reviewed it
                    {server.confirmedCatalogDigest ? "" : " (it has never been confirmed)"}. Tools advertised as
                    read-only by the server stay disabled until you review and confirm the catalog.
                  </p>
                  {(() => {
                    const s = catalogChangeSummary(server.lifecycle);
                    if (!s) return null;
                    return (
                      <p className="text-[10px] font-mono text-amber-300/80">
                        {s.count} catalog change{s.count === 1 ? "" : "s"} this session
                        {s.formattedWhen ? ` · last ${s.formattedWhen}` : ""}
                      </p>
                    );
                  })()}
                </div>
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
                {server.state === "lazy"
                  ? "Lazy server: tool declarations load from the on-disk cache; it is NOT connected until first use (the first call connects)."
                  : server.enabled ? "No tools discovered (the server may have failed — see the diagnostic above)." : "Enable the server to discover its tools."}
              </p>
            ) : (
              <div className="divide-y divide-border/10">
                {server.tools.map((tool) => {
                  const declared = server.toolEffects[tool.originalName];
                  const activatable = tool.activatable;
                  // In exclude mode the runtime decides selection by the live
                  // globs; the editor must not imply a manual selection.
                  const globMode = !Array.isArray(server.selectedTools);
                  const globs = globMode
                    ? (server.selectedTools as { include: string[]; exclude: string[] })
                    : null;
                  const selected = globMode
                    ? resolveSelectedByGlobs(tool.originalName, globs?.include ?? [], globs?.exclude ?? [])
                    : tool.selected || selectedToolNames(server).includes(tool.originalName);
                  return (
                    <label key={tool.originalName} className={cn("flex items-start gap-3 px-4 py-2.5", activatable ? "cursor-pointer hover:bg-accent/20" : "opacity-70")}>
                      <input
                        type="checkbox"
                        className="mt-0.5 accent-primary"
                        checked={selected}
                        disabled={!activatable || busy || globMode}
                        onChange={(e) => activatable && onSelectTool(tool.originalName, e.target.checked)}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-mono text-foreground">{tool.originalName}</span>
                          <EffectBadge effect={declared ?? tool.effect} />
                          {declared && <span className="text-[9px] font-mono text-emerald-300">declared</span>}
                          <span className="text-[9px] font-mono text-muted-foreground">→ {tool.eclipseName}</span>
                          {selected && activatable && <span className="text-[9px] text-primary">active</span>}
                          {globMode && <span className="text-[9px] font-mono text-muted-foreground">selected by your include/exclude globs</span>}
                        </div>
                        {tool.description && <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">{tool.description}</p>}
                        {tool.note && <p className="text-[10px] text-amber-300 mt-0.5">{tool.note}</p>}
                        {!activatable && tool.diagnostic && <p className="text-[10px] text-rose-400 mt-0.5">{tool.diagnostic}</p>}
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

/** A compact one-line lifecycle summary (the detail is in the panel below). */
function lifecycleSummary(server: MCPServerView): React.ReactNode {
  const l = server.lifecycle;
  if (!l) return null;
  const parts: string[] = [];
  if (l.lazyActive) parts.push(`lazy (${l.cachedTools ?? 0} cached)`);
  if (l.lastErrorCode) parts.push(`last error: ${l.lastErrorCode}`);
  if (l.keepaliveFailures) parts.push(`${l.keepaliveFailures} keepalive failure(s)`);
  if (l.recycledReason) parts.push(`recycled: ${l.recycledReason}`);
  if (parts.length === 0) return null;
  return <p className="text-[10px] font-mono text-amber-300">{parts.join(" · ")}</p>;
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

  const draftToPayload = (d: DraftServer) => draftToInput(d);

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
      // Build the full payload from the extracted mapping so a card-level
      // toggle can never drop a Phase-6 field. `env` is intentionally omitted
      // (the mapping yields no values for stored keys), so the runtime merges
      // and preserves the stored secrets.
      const draft = draftFromServer(server);
      const input = draftToInput(draft).server;
      const res = await fetch("/api/harness/mcp/servers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          server: {
            ...input,
            enabled: patch.enabled ?? input.enabled,
            selectedTools: patch.selectedTools ?? input.selectedTools,
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
    setEditing(draftFromServer(server));
  };

  const oauthLogin = async (server: MCPServerView): Promise<{ verificationUri?: string; userCode?: string }> => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/harness/mcp/servers/${encodeURIComponent(server.id)}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Sign-in failed");
      await load();
      return { verificationUri: body.verificationUri, userCode: body.userCode };
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
      return {};
    } finally {
      setBusy(false);
    }
  };

  const verifyServer = async (server: MCPServerView, tool: string, args: Record<string, unknown>): Promise<MCPVerifyResult | { error: string }> => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/harness/mcp/servers/${encodeURIComponent(server.id)}/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool, arguments: args }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Verify failed");
      await load();
      return body as MCPVerifyResult;
    } catch (err) {
      return { error: err instanceof Error ? err.message : "Verify failed" };
    } finally {
      setBusy(false);
    }
  };

  const resetCircuit = async (server: MCPServerView) => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/harness/mcp/servers/${encodeURIComponent(server.id)}/circuit/reset`, { method: "POST" });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Circuit reset failed");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Circuit reset failed");
    } finally {
      setBusy(false);
    }
  };

  const oauthLogout = async (server: MCPServerView) => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/harness/mcp/servers/${encodeURIComponent(server.id)}/logout`, { method: "POST" });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Sign-out failed");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-out failed");
    } finally {
      setBusy(false);
    }
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
        onInstalled={() => void load()}
      />
      <MCPDiagnosticsPanel busy={busy} />

      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground font-mono">
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
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 mb-4">
          <div className="flex items-start gap-2">
            <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-[11px] font-semibold text-rose-300">
                {loadDiagnostics.length} server config entr{loadDiagnostics.length === 1 ? "y" : "ies"} could not be loaded.
              </p>
              <p className="text-[11px] text-muted-foreground mt-1">
                A malformed entry in mcp-servers.json is skipped rather than crashing startup. Fix the file to
                configure {loadDiagnostics.length === 1 ? "it" : "them"}.
              </p>
              <ul className="mt-1.5 space-y-0.5">
                {loadDiagnostics.map((d, i) => (
                  <li key={`${d.server}:${d.code}:${i}`} className="text-[10px] font-mono text-muted-foreground">
                    {d.server} ({d.code}): {d.message}
                  </li>
                ))}
              </ul>
            </div>
          </div>
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
                const current = selectedToolNames(server);
                const next = selected
                  ? [...current, tool]
                  : current.filter((t) => t !== tool);
                void updateServer(server, { selectedTools: next });
              }}
              onRemove={() => void removeServer(server)}
              onEdit={() => editServer(server)}
              onConfirmCatalog={() => void confirmCatalog(server)}
              onOauthLogin={() => oauthLogin(server)}
              onOauthLogout={() => void oauthLogout(server)}
              onVerify={(tool, args) => verifyServer(server, tool, args)}
              onResetCircuit={() => void resetCircuit(server)}
            />
          ))}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 mt-5">
        <MCPSecretsPanel busy={busy} onError={setError} />
        <MCPApprovalsPanel busy={busy} onError={setError} />
      </div>

      <MCPSupplyChainPanel />

      <p className="text-[10px] text-muted-foreground/60 mt-4 leading-relaxed">
        Local stdio and remote HTTP/SSE servers, OAuth sign-in, resources/prompts, lazy start, TLS/mTLS and
        per-call effectful-tool approvals are implemented here. Eclipse acting as an MCP server is configured
        outside this panel. Subscriptions remain a documented non-goal: a notification never triggers a run or a write.
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


// ── Supply chain (read-only, offline) ───────────────────────────────────────
function MCPSupplyChainPanel() {
  const [report, setReport] = useState<MCPSupplyChainReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/harness/mcp/supply-chain");
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Supply-chain report failed");
        return;
      }
      setReport(body);
    } catch {
      setError("Could not reach the supply-chain endpoint");
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <Panel className="p-5 mt-4">
      <button type="button" className="flex w-full items-center justify-between cursor-pointer" onClick={() => { setOpen((o) => !o); if (!open && !report) void load(); }}>
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">Supply chain</h3>
          <span className="text-[10px] text-muted-foreground">offline report — no network call</span>
        </div>
        <ChevronDown className={cn("w-4 h-4 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          {loading && <p className="text-[11px] text-muted-foreground flex items-center gap-2"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…</p>}
          {error && <p className="text-[11px] text-rose-400">{error}</p>}
          {report && (
            <>
              <p className="text-[10px] text-muted-foreground">{report.note}</p>
              <p className="text-[10px] text-muted-foreground/70">
                This report never contacts the network. The date shown is when an entry was last reviewed, not a
                live version check, so it does not imply the package is current.
              </p>
              {report.packages.length === 0 ? (
                <p className="text-[11px] text-muted-foreground/70">No packages to report.</p>
              ) : (
                <>
                  <p className="text-[10px] text-muted-foreground">
                    {report.packages.length} package(s) · {report.unpinnedCount} unpinned · generated {report.generatedAt ?? report.checkedAt}
                    {report.upstreamChecked ? " · at least one live OSV check recorded" : ""}
                  </p>
                  <div className="rounded-xl border border-border/20 divide-y divide-border/10">
                    {report.packages.map((p) => {
                      const live = p.liveVerdict;
                      return (
                        <div key={`${p.source}:${p.package}`} className="flex flex-col gap-1 px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] font-mono text-foreground truncate">{p.package}</span>
                            <span className={cn("text-[9px] font-bold uppercase", p.pinned ? "text-emerald-400" : "text-amber-300")}>
                              {p.pinned ? "pinned" : "unpinned"}
                            </span>
                            <span className="text-[9px] font-mono text-muted-foreground">{p.source}</span>
                            <span className="text-[9px] font-mono text-muted-foreground" title="last reviewed, not live-checked">
                              reviewed {p.checkedAt}
                            </span>
                          </div>
                          {live ? (
                            <div className="flex items-center gap-2 flex-wrap text-[9px] font-mono">
                              <span className={cn("font-bold uppercase",
                                live.code === "blocked" ? "text-rose-400"
                                  : live.code === "unknown" ? "text-amber-300" : "text-emerald-400")}>
                                live: {live.code}
                              </span>
                              {live.advisoryIds.length > 0 && (
                                <span className="text-rose-300">advisories {live.advisoryIds.join(", ")}</span>
                              )}
                              {live.code === "unknown" && live.reason && (
                                <span className="text-amber-300/80">{live.reason}</span>
                              )}
                              <span className="text-muted-foreground">checked {live.checkedAt}</span>
                            </div>
                          ) : (
                            <span className="text-[9px] font-mono text-muted-foreground/60">
                              no live check recorded (the spawn path checks at launch)
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}
    </Panel>
  );
}

// -- Finance workflow wizard (task-oriented setup) ---------------------------

function FinanceWorkflowWizard({
  busy,
  onAddServer,
  onInstalled,
}: {
  busy: boolean;
  onAddServer: (draft: DraftServer) => void;
  onInstalled: () => void;
}) {
  const [workflows, setWorkflows] = useState<MCPWorkflowView[]>([]);
  const [integrations, setIntegrations] = useState<MCPIntegrationView[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [installMsg, setInstallMsg] = useState<Record<string, string>>({});

  const onInstall = async (integrationId: string) => {
    try {
      const res = await fetch(`/api/harness/mcp/integrations/${encodeURIComponent(integrationId)}/install`, { method: "POST" });
      const body = await res.json();
      if (!res.ok) {
        setInstallMsg((m) => ({ ...m, [integrationId]: body.error ?? "Install failed" }));
        return;
      }
      setInstallMsg((m) => ({
        ...m,
        [integrationId]: body.alreadyInstalled
          ? "Already configured — left unchanged."
          : "Installed as a DISABLED entry with nothing selected. Open its card to add the secret or sign in, test, then select tools. Install is not activation.",
      }));
      onInstalled();
    } catch {
      setInstallMsg((m) => ({ ...m, [integrationId]: "Install request failed" }));
    }
  };

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
      name: spec.label,
      transport: spec.transport,
      command: spec.command ?? "",
      argsText: (spec.args ?? []).join("\n"),
      url: spec.url ?? "",
      authKind: spec.oauth ? "oauth" : "header",
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
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-[11px] text-foreground">{spec.label}</span>
                            {!spec.verified && <span className="text-[9px] text-amber-300">template (unverified)</span>}
                            {spec.verified && spec.community && <span className="text-[9px] text-muted-foreground">community</span>}
                            {spec.oauth && <span className="text-[9px] text-sky-300">OAuth sign-in</span>}
                          </div>
                          <p className="text-[10px] text-muted-foreground mt-0.5 max-w-xs">{spec.purpose}</p>
                          {spec.verified && spec.verified_at && (
                            <p className="text-[9px] text-muted-foreground/80 mt-0.5">
                              verified {spec.verified_at}{spec.verified_against ? ` against ${spec.verified_against}` : ""}
                            </p>
                          )}
                          {spec.notes && <p className="text-[9px] text-muted-foreground/70 mt-0.5 max-w-xs">{spec.notes}</p>}
                          {spec.secret_label && <p className="text-[9px] text-muted-foreground/80 mt-0.5">Needs: {spec.secret_label}</p>}
                          <div className="flex items-center gap-1.5 mt-1.5">
                            <Button
                              size="sm" variant="outline" className="h-6 cursor-pointer rounded-lg text-[10px]"
                              disabled={busy}
                              onClick={() => void onInstall(id)}
                            >
                              Install (disabled)
                            </Button>
                            <Button
                              size="sm" variant="ghost" className="h-6 cursor-pointer rounded-lg text-[10px]"
                              disabled={busy}
                              onClick={() => onAddServer(draftFromIntegration(id))}
                            >
                              Set up manually
                            </Button>
                          </div>
                          {installMsg[id] && (
                            <p className="text-[9px] text-emerald-300 mt-1 max-w-xs">{installMsg[id]}</p>
                          )}
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
