"use client";

import { useState } from "react";
import { Check, CircleDashed, ExternalLink, Loader2, ShieldCheck } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { SetupKeyStatuses, SetupSourceRow } from "../types";
import { LicenseBadge } from "./license-badge";
import { commercialSentence } from "@/lib/setup/source-catalog";

export function ProviderCard({
  source,
  status,
  onSaveKey,
  compact,
}: {
  source: SetupSourceRow;
  status?: SetupKeyStatuses[string];
  onSaveKey: (envVar: string, value: string) => Promise<string>;
  compact?: boolean;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const configured = Boolean(status?.configured);

  const save = async () => {
    if (!source.envVar || !value.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await onSaveKey(source.envVar, value.trim());
      setMessage(result);
      if (!/fail|error/i.test(result)) setValue("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={cn("rounded-xl border border-white/10 bg-white/[0.02]", compact ? "p-2.5" : "p-3")}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold text-foreground">{source.label}</span>
        <LicenseBadge status={source.commercial} />
        <span
          className={cn(
            "ml-auto inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-bold",
            configured
              ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300"
              : "border-white/10 text-muted-foreground",
          )}
        >
          {configured ? <Check size={9} /> : <CircleDashed size={9} />}
          {configured ? "Connected" : "Not connected"}
        </span>
      </div>
      <p
        className={cn(
          "mt-1 text-[9px] font-semibold leading-snug",
          source.commercial === "personal-only"
            ? "text-rose-300"
            : source.commercial === "verify"
              ? "text-amber-300"
              : "text-emerald-300/90",
        )}
      >
        {commercialSentence(source.commercial)}
      </p>
      <p className="mt-0.5 text-[10px] leading-relaxed text-muted-foreground">{source.note}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={configured ? "Replace stored key" : "Paste your API key"}
          className="h-7 max-w-[240px] text-[11px]"
          autoComplete="off"
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="cursor-pointer rounded-lg text-[11px]"
          disabled={busy || !value.trim()}
          onClick={() => void save()}
        >
          {busy ? <Loader2 size={11} className="animate-spin" /> : <ShieldCheck size={11} />}
          Save key
        </Button>
        {source.termsUrl && (
          <a
            href={source.termsUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-[9px] text-muted-foreground hover:text-foreground"
          >
            Terms <ExternalLink size={9} />
          </a>
        )}
      </div>
      {message && <p className="mt-1.5 text-[9px] text-muted-foreground">{message}</p>}
    </div>
  );
}
