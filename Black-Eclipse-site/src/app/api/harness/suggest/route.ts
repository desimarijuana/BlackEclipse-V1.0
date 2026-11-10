// GET /api/harness/suggest?provider=skills&q=crypto&limit=8
//
// Argument completion for the composer's command palette. This is a hint
// surface only: it never executes anything and a slow/unavailable subsystem
// degradesto an empty list rather than an error toast.

import { NextResponse } from "next/server";
import { listSkills } from "@/lib/harness/skills-client";
import { listPortfolios } from "@/lib/harness/portfolio-client";
import { listWorkflows } from "@/lib/harness/workflows-client";
import { listModelProviders } from "@/lib/harness/python-client";
import { getAllInstruments } from "@/lib/search/registry";
import type { CommandSuggestion } from "@/lib/harness/command-suggest-types";

export const dynamic = "force-dynamic";

const PROVIDERS = new Set(["skills", "symbols", "portfolios", "workflows", "models"]);
const DEADLINE_MS = 2_500;

function withDeadline<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("suggestion provider timed out")), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (err: unknown) => {
        clearTimeout(timer);
        reject(err);
      },
    );
  });
}

function matches(haystack: Array<string | null | undefined>, query: string): boolean {
  if (!query) return true;
  return haystack.filter(Boolean).some((value) => String(value).toLowerCase().includes(query));
}

async function loadCandidates(provider: string, query: string, limit: number): Promise<CommandSuggestion[]> {
  switch (provider) {
    case "skills": {
      const { skills } = await listSkills();
      return skills
        .filter((skill) => matches([skill.id, skill.name, skill.description, skill.category], query))
        .slice(0, limit)
        .map((skill) => ({ value: skill.id, label: skill.name || skill.id, subtitle: skill.description }));
    }
    case "symbols": {
      return getAllInstruments()
        .filter((instrument) => matches([instrument.symbol, instrument.title], query))
        .slice(0, limit)
        .map((instrument) => ({
          value: instrument.symbol || instrument.title,
          label: instrument.symbol || instrument.title,
          subtitle: instrument.title,
        }));
    }
    case "portfolios": {
      return (await listPortfolios())
        .filter((portfolio) => matches([portfolio.id, portfolio.name, portfolio.description], query))
        .slice(0, limit)
        .map((portfolio) => ({ value: portfolio.id, label: portfolio.name, subtitle: portfolio.baseCurrency }));
    }
    case "workflows": {
      return (await listWorkflows())
        .filter((workflow) => matches([workflow.id, workflow.name, workflow.description], query))
        .slice(0, limit)
        .map((workflow) => ({
          value: workflow.id,
          label: workflow.name || workflow.id,
          subtitle: workflow.description ?? undefined,
        }));
    }
    case "models": {
      return (await listModelProviders())
        .filter((row) => matches([String(row.id ?? ""), String(row.label ?? row.name ?? "")], query))
        .slice(0, limit)
        .map((row) => ({
          value: String(row.id ?? ""),
          label: String(row.label ?? row.name ?? row.id ?? ""),
          subtitle: Array.isArray(row.models) ? `${row.models.length} models` : undefined,
        }))
        .filter((row) => Boolean(row.value));
    }
    default:
      return [];
  }
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const provider = (url.searchParams.get("provider") ?? "").trim().toLowerCase();
  const query = (url.searchParams.get("q") ?? "").trim().toLowerCase();
  const limit = Math.min(20, Math.max(1, Number(url.searchParams.get("limit") ?? 8) || 8));

  if (!PROVIDERS.has(provider)) {
    return NextResponse.json({ candidates: [], error: "unknown provider" }, { status: 400 });
  }

  try {
    const candidates = await withDeadline(loadCandidates(provider, query, limit), DEADLINE_MS);
    return NextResponse.json({ candidates });
  } catch {
    // The composer degrades silently; it must never block typing on a down runtime.
    return NextResponse.json({ candidates: [], unavailable: true });
  }
}
