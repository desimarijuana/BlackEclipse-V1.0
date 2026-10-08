"use client";

// ── Search retrieval settings ───────────────────────────────────────────────
// One place to make evidence-based research retrieval dependable:
//
//   1. Search providers — each named provider (Tavily/Brave/Exa/Serper/
//      SerpApi/Bing/Google CSE/SearXNG) gets its own editor, so a user adds
//      exactly one key (no JSON) and it is preferred over the keyless chain. The
//      keyless DuckDuckGo/Mojeek/Bing HTML chain always stays as fallback.
//   2. JS rendering — one click downloads the Playwright Chromium binary so
//      JavaScript-only pages (and many login walls) can be rendered.
//
// Honesty rules: the key value never crosses this boundary (only a masked hint);
// the connectivity test reports what really happened per provider; the browser
// install reports the binary's true presence, never a silent success.

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Download, Globe, Loader2, Play, Search as SearchIcon, Zap } from "@/lib/icons";
import { Panel, SubSection } from "./settings-ui";
import { ProviderKeyEditor } from "./provider-registry-panel";
import type { ProviderKeyStatus } from "@/lib/provider-keys";

interface Preset {
  id: string;
  name: string;
  keyUrl: string;
  keyEnv: string;
  publicValue?: boolean;
}

interface TestResult {
  ok: boolean;
  provider: string | null;
  configuredProvider: string | null;
  resultCount: number;
  sample: Array<{ title: string; url: string }>;
  diagnostics: Array<{ provider: string; category: string; detail: string; latencyMs: number }>;
}

interface InstallStatus {
  installed: boolean;
  reason?: string | null;
}

export function SearchRetrievalSettings() {
  const [keys, setKeys] = useState<ProviderKeyStatus[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<TestResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [install, setInstall] = useState<InstallStatus | null>(null);
  const [installing, setInstalling] = useState(false);

  const refreshKeys = useCallback(async () => {
    try {
      const res = await fetch("/api/provider-keys");
      const body = (await res.json()) as { keys?: ProviderKeyStatus[] };
      setKeys(body.keys ?? []);
    } catch {
      setKeys([]);
    }
  }, []);

  useEffect(() => {
    void refreshKeys();
    void fetch("/api/search-provider")
      .then((r) => r.json())
      .then((b: { presets?: Preset[] }) => setPresets(b.presets ?? []))
      .catch(() => setPresets([]));
    void fetch("/api/search-provider/install")
      .then((r) => r.json())
      .then((b: InstallStatus) => setInstall(b))
      .catch(() => setInstall(null));
  }, [refreshKeys]);

  const runTest = useCallback(async () => {
    setTesting(true);
    setTest(null);
    try {
      const res = await fetch("/api/search-provider", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      setTest((await res.json()) as TestResult);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Search test failed");
    } finally {
      setTesting(false);
    }
  }, []);

  const enableJs = useCallback(async () => {
    setInstalling(true);
    setMessage(null);
    try {
      const res = await fetch("/api/search-provider/install", { method: "POST" });
      const body = (await res.json()) as InstallStatus & { error?: string };
      setInstall(body);
      if (!res.ok || !body.installed) {
        setMessage(body.error ?? "The browser could not be installed. See the runtime log for details.");
      } else {
        setMessage("JavaScript rendering enabled — the Chromium browser is installed.");
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "The browser could not be installed");
    } finally {
      setInstalling(false);
    }
  }, []);

  const configured = presets.filter((p) => keys.find((k) => k.envVar === p.keyEnv)?.configured);

  return (
    <div className="space-y-6">
      <SubSection
        icon={SearchIcon}
        title="Web search providers"
        description="Add any ONE provider key to prefer a dependable, keyed API. The keyless DuckDuckGo/Mojeek/Bing HTML chain is always tried as fallback, so configuration is optional."
      >
        <Panel className="p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[10px] text-muted-foreground">
              {configured.length > 0
                ? `${configured.map((p) => p.name).join(", ")} configured — used before the keyless chain.`
                : "No provider key yet — using the keyless chain."}
            </p>
            <Button
              variant="outline"
              size="sm"
              className="cursor-pointer rounded-xl text-[11px] h-8"
              onClick={runTest}
              disabled={testing}
            >
              {testing ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Play className="w-3.5 h-3.5 mr-1" />}
              Test search
            </Button>
          </div>

          {test && (
            <div className="rounded-xl border border-border/20 glass-card-subtle p-3 space-y-1">
              <p className={cn("text-[11px] font-medium", test.ok ? "text-emerald-400" : "text-amber-400")}>
                {test.ok
                  ? `Answered by ${test.provider} (${test.resultCount} result${test.resultCount === 1 ? "" : "s"})`
                  : "No provider returned results — see per-provider diagnostics"}
              </p>
              {test.sample.map((s) => (
                <p key={s.url} className="text-[10px] text-muted-foreground truncate">
                  {s.title} — {s.url}
                </p>
              ))}
              {test.diagnostics.map((d, i) => (
                <p key={`${d.provider}-${i}`} className="text-[10px] text-muted-foreground/80 font-mono">
                  {d.provider}: {d.category}
                  {d.detail ? ` (${d.detail})` : ""}
                </p>
              ))}
            </div>
          )}

          {message && <p className="text-[10px] text-muted-foreground">{message}</p>}

          <div className="space-y-2">
            {presets.map((p) => (
              <div key={p.id} className="space-y-1">
                <p className="text-[10px] text-muted-foreground">
                  {p.name} —{" "}
                  <a className="text-primary underline" href={p.keyUrl} target="_blank" rel="noreferrer">
                    get a key
                  </a>
                </p>
                <ProviderKeyEditor
                  envVar={p.keyEnv}
                  label={p.publicValue ? `${p.name} (base URL)` : p.name}
                  onChanged={refreshKeys}
                />
              </div>
            ))}
          </div>

          <p className="text-[10px] text-muted-foreground/70 leading-relaxed">
            Keys are encrypted at rest and never returned to the browser. Advanced JSON configuration
            remains available for a custom endpoint (see the custom search API keys below).
          </p>
        </Panel>
      </SubSection>

      <SubSection
        icon={Globe}
        title="JavaScript rendering"
        description="Many modern pages render only in a browser. Enable it once to render JavaScript-only pages and reach some login-gated sources; a missing browser is always reported honestly."
      >
        <Panel className="p-5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 min-w-0">
            <Zap className={cn("w-4 h-4 shrink-0", install?.installed ? "text-emerald-400" : "text-muted-foreground")} />
            <div className="min-w-0">
              <p className="text-xs font-medium text-foreground">
                {install?.installed ? "Browser installed" : install ? "Browser not installed" : "Status unknown"}
              </p>
              <p className="text-[10px] text-muted-foreground truncate">
                {install?.installed
                  ? "JavaScript-only pages can be rendered during research."
                  : install?.reason || "One-time download of the Chromium browser (~150 MB)."}
              </p>
            </div>
          </div>
          <Button
            variant={install?.installed ? "outline" : "default"}
            size="sm"
            className="cursor-pointer rounded-xl text-[11px] h-9 shrink-0"
            onClick={enableJs}
            disabled={installing || install?.installed}
          >
            {installing ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Download className="w-3.5 h-3.5 mr-1" />}
            {install?.installed ? "Enabled" : "Enable JS rendering"}
          </Button>
        </Panel>
      </SubSection>
    </div>
  );
}
