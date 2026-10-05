"use client";

// ── MCP credential verification card (MCP integrity, Phase 1b) ──────────────
// The operator-triggered Verify action is separate from Test. Test only proves
// the process started and listed tools; Verify makes ONE bounded read call with
// operator-supplied arguments to prove the credential actually works. It is
// never automatic, never at boot, and never in a loop. The response body is
// never shown — only a content-free verdict, which can be checked while the
// server is connected (a server can be connected AND rejected).

import { useState } from "react";
import { Loader2 } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import type { MCPServerView, MCPVerifyResult } from "@/lib/harness/mcp-types";

export function CredentialsPanel({
  server,
  busy,
  onVerify,
}: {
  server: MCPServerView;
  busy: boolean;
  onVerify: (tool: string, args: Record<string, unknown>) => Promise<MCPVerifyResult | { error: string }>;
}) {
  const [verifyResult, setVerifyResult] = useState<MCPVerifyResult | { error: string } | null>(null);
  const [verifying, setVerifying] = useState(false);
  // Verify must use a READ tool; only declared read tools are offered.
  const readTools = server.tools.filter((t) => (server.toolEffects[t.originalName] ?? t.effect) === "read");
  const [verifyTool, setVerifyTool] = useState<string>("");
  const [verifyArgs, setVerifyArgs] = useState("{}");
  const effectiveVerifyTool = verifyTool || readTools[0]?.originalName || "";
  const verify = server.lifecycle?.verify ?? null;

  const runVerify = async () => {
    if (!effectiveVerifyTool) return;
    setVerifying(true);
    setVerifyResult(null);
    try {
      let parsed: Record<string, unknown> = {};
      try {
        parsed = verifyArgs.trim() ? (JSON.parse(verifyArgs) as Record<string, unknown>) : {};
      } catch {
        setVerifyResult({ error: "Arguments must be valid JSON" });
        return;
      }
      setVerifyResult(await onVerify(effectiveVerifyTool, parsed));
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="rounded-xl border border-border/20 glass-card-subtle px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Credentials</span>
        {verify?.code === "credentials_valid" && <span className="text-[10px] font-bold text-emerald-400">VALID</span>}
        {verify?.code === "credentials_rejected" && (
          <span className="text-[10px] font-bold text-rose-400">
            REJECTED{verify.providerStatus ? ` (status ${verify.providerStatus})` : ""}{verify.providerCode ? ` · ${verify.providerCode}` : ""}
          </span>
        )}
        {verify?.code === "verify_inconclusive" && <span className="text-[10px] font-bold text-amber-300">INCONCLUSIVE</span>}
      </div>
      <p className="text-[10px] text-muted-foreground leading-relaxed">
        A server can be <strong>connected</strong> and still reject its credentials. <strong>Test</strong> only proves the process
        started and listed tools — it never checks a credential. <strong>Verify</strong> makes one read call with your tool and
        arguments to prove the credential works; it is opt-in and never runs automatically.
      </p>
      {verify?.verifiedAt && (
        <p className="text-[9px] font-mono text-muted-foreground">
          last verified {verify.verifiedAt} with <span className="text-foreground">{verify.tool}</span>
          {verify.reason ? ` · ${verify.reason}` : ""}
        </p>
      )}
      {readTools.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <select
              value={effectiveVerifyTool}
              onChange={(e) => setVerifyTool(e.target.value)}
              className="rounded-lg border border-border/40 bg-background/60 px-2 py-1 text-[11px] font-mono text-foreground"
            >
              {readTools.map((t) => (
                <option key={t.originalName} value={t.originalName}>{t.originalName}</option>
              ))}
            </select>
            <input
              value={verifyArgs}
              onChange={(e) => setVerifyArgs(e.target.value)}
              placeholder='arguments JSON, e.g. {"query":"x"}'
              className="flex-1 rounded-lg border border-border/40 bg-background/60 px-2 py-1 text-[11px] font-mono text-foreground"
            />
            <Button size="sm" variant="outline" className="cursor-pointer rounded-xl" onClick={() => void runVerify()} disabled={busy || verifying}>
              {verifying ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : null} Verify
            </Button>
          </div>
          <p className="text-[9px] text-muted-foreground/70">
            Declare a read tool and its effect first; Verify will never call a write tool.
          </p>
        </div>
      ) : (
        <p className="text-[10px] text-muted-foreground/70">Select and declare a read tool to enable Verify.</p>
      )}
      {verifyResult && "error" in verifyResult && <p className="text-[10px] text-rose-400">{verifyResult.error}</p>}
    </div>
  );
}
