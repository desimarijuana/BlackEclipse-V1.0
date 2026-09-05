// Research orchestrator — the "Hermes-style" multi-agent research engine.
//
// Flow:
//   1. Parse the user's query to detect a ticker + market + intent.
//   2. Run specialized agents in parallel (news, fundamentals, technical, risk),
//      each with its own system prompt and the shared tool set.
//   3. Synthesize all agent outputs into a single decision-oriented report.
//   4. Persist the report + agent runs + findings to JDDS (research memory).
//
// Each agent uses the same tool-calling loop, so it can search the web, pull
// live prices, read news, and check source health on its own.

import { prisma } from "@/lib/db";
import { runAgent } from "./loop";
import { getTool } from "./tools";

// Single agent entry point: research uses the same OpenAICompatibleProvider
// the registry serves through /api/agent/chat — one provider implementation.
import { OpenAICompatibleProvider } from "./openai-provider";

export interface ResearchRequest {
  query: string;
  ticker?: string;
  market?: string;
}

export interface ResearchResult {
  reportId: string;
  answer: string;
  verdict?: string;
  confidence?: number;
  agents: { name: string; status: string; toolCalls: number; toolErrors: number }[];
}

// ─── Query parsing ────────────────────────────────────────────────────
// Detect a likely ticker (uppercase 1-5 letters) and market from the query.
const MARKET_HINTS: Record<string, string> = {
  pakistan: "PK", psx: "PK", karachi: "PK", kse: "PK",
  india: "IN", nse: "IN", bse: "IN",
  crypto: "CRYPTO", bitcoin: "CRYPTO", ethereum: "CRYPTO",
  china: "CN", hong: "CN",
};

export function parseQuery(query: string): { ticker?: string; market?: string } {
  const lower = query.toLowerCase();
  let market: string | undefined;
  for (const [hint, m] of Object.entries(MARKET_HINTS)) {
    if (lower.includes(hint)) {
      market = m;
      break;
    }
  }

  // Ticker: a standalone uppercase token (2-5 letters) that isn't a common word.
  const tokens = query.match(/\b[A-Z]{2,5}\b/g) || [];
  const stop = new Set(["AI", "US", "PK", "IN", "CN", "ETF", "IPO", "PE", "EPS", "ROE", "ROI", "GDP", "CEO", "CFO", "YOY", "Q1", "Q2", "Q3", "Q4", "PSX", "KSE", "NSE", "BSE", "NYSE", "NASDAQ"]);
  const ticker = tokens.find((t) => !stop.has(t));

  return { ticker, market };
}

// ─── Agent definitions ────────────────────────────────────────────────
interface AgentSpec {
  name: string;
  systemPrompt: (ctx: { ticker?: string; market?: string; query: string }) => string;
}

const AGENTS: AgentSpec[] = [
  {
    name: "news",
    systemPrompt: ({ ticker, market, query }) =>
      `You are the NEWS & SENTIMENT research agent for BlackEclipse, a finance research platform.
Your job: gather recent news and sentiment about the target and report what you find.
Use the get_news and search_web tools to find headlines, and get_price for context.
Target: ${ticker || "the subject of: " + query}${market ? ` (market: ${market})` : ""}
Report back a concise summary of: key headlines, overall sentiment (bullish/bearish/neutral),
and any catalysts or risks mentioned. Cite sources. Do NOT give a buy/sell recommendation.`,
  },
  {
    name: "fundamentals",
    systemPrompt: ({ ticker, market, query }) =>
      `You are the FUNDAMENTALS research agent for BlackEclipse.
Your job: gather fundamental data about the target company/asset.
Use get_fundamentals, get_price, and search_web to find financial health, sector, industry,
valuation context, and growth drivers.
Target: ${ticker || "the subject of: " + query}${market ? ` (market: ${market})` : ""}
Report back: sector/industry, business description, key financials you can find,
and growth vectors. Note where data is missing. Do NOT give a buy/sell recommendation.`,
  },
  {
    name: "technical",
    systemPrompt: ({ ticker, market, query }) =>
      `You are the TECHNICAL research agent for BlackEclipse.
Your job: analyze price action and technicals for the target.
Use get_price to get the latest price/change, and search_web for technical analysis context.
Target: ${ticker || "the subject of: " + query}${market ? ` (market: ${market})` : ""}
Report back: current price, recent change, momentum, and any support/resistance or trend
observations you can infer. Note that historical OHLC may be limited. Do NOT give a buy/sell recommendation.`,
  },
  {
    name: "risk",
    systemPrompt: ({ ticker, market, query }) =>
      `You are the RISK research agent for BlackEclipse.
Your job: assess the risks of investing in the target.
Use get_price, get_news, get_source_health, and search_web to identify risks:
volatility, sector/regulatory risks, data reliability, concentration, and downside catalysts.
Target: ${ticker || "the subject of: " + query}${market ? ` (market: ${market})` : ""}
Report back a concise risk list with severity (low/medium/high). Do NOT give a buy/sell recommendation.`,
  },
];

// ─── Orchestrator ─────────────────────────────────────────────────────
const ORCHESTRATOR_PROMPT = (ctx: { ticker?: string; market?: string; query: string }) =>
  `You are the ORCHESTRATOR / synthesizer for BlackEclipse, an agentic finance research platform.
You have received research from specialized agents (news, fundamentals, technical, risk).
Your job: combine their findings into ONE clear, decision-oriented research report for the user.

User's original request: "${ctx.query}"
Target: ${ctx.ticker || "the subject of the query"}${ctx.market ? ` (market: ${ctx.market})` : ""}

Produce a report with these sections:
1. **Executive Summary** — 2-3 sentences: what the asset is and the bottom line.
2. **Key Findings** — bullet points combining the agents' data (fundamentals, news, technicals, risks).
3. **Risks** — the most important risks, with severity.
4. **Verdict** — a clear stance: BULLISH / BEARISH / NEUTRAL / HOLD, with a confidence level (0-100%).
5. **What to watch** — 2-3 catalysts or data points to monitor.

Be honest about missing data. This is research to help the user decide — be balanced, not promotional.
End with a one-line disclaimer that this is not financial advice.`;

// ─── Runner ───────────────────────────────────────────────────────────
export async function runResearch(req: ResearchRequest): Promise<ResearchResult> {
  const provider = new OpenAICompatibleProvider();
  const parsed = parseQuery(req.query);
  const ticker = req.ticker || parsed.ticker;
  const market = req.market || parsed.market;

  // Create the report record (research memory).
  const report = await prisma.researchReport.create({
    data: { query: req.query, ticker: ticker || null, market: market || null, status: "running" },
  });

  const ctx = { ticker, market, query: req.query };
  const agentResults: { name: string; status: string; toolCalls: number; toolErrors: number; output: string }[] = [];

  // Run specialized agents in parallel.
  const runs = await Promise.allSettled(
    AGENTS.map(async (spec) => {
      const run = await prisma.agentRun.create({
        data: { reportId: report.id, agent: spec.name, status: "running" },
      });
      let toolCalls = 0;
      let toolErrors = 0;
      let output = "";
      try {
        const result = await runAgent(
          provider,
          spec.systemPrompt(ctx),
          req.query,
          {
            maxIterations: 6,
            onToolCall: (call, res) => {
              toolCalls++;
              if (res.startsWith("Tool error") || res.startsWith("Unknown tool")) toolErrors++;
              // Persist a finding for memory/citation.
              prisma.researchFinding
                .create({
                  data: {
                    reportId: report.id,
                    agent: spec.name,
                    kind: call.name,
                    ticker: ticker || null,
                    title: call.name,
                    detail: res.slice(0, 500),
                    source: call.name,
                  },
                })
                .catch(() => {});
            },
          }
        );
        output = result.answer;
        await prisma.agentRun.update({
          where: { id: run.id },
          data: { status: "done", toolCalls, toolErrors, output, finishedAt: new Date() },
        });
        return { name: spec.name, status: "done", toolCalls, toolErrors, output };
      } catch (err) {
        output = `Agent failed: ${err instanceof Error ? err.message : String(err)}`;
        await prisma.agentRun.update({
          where: { id: run.id },
          data: { status: "failed", toolCalls, toolErrors, output, finishedAt: new Date() },
        });
        return { name: spec.name, status: "failed", toolCalls, toolErrors, output };
      }
    })
  );

  for (const r of runs) {
    if (r.status === "fulfilled") agentResults.push(r.value);
    else agentResults.push({ name: "unknown", status: "failed", toolCalls: 0, toolErrors: 0, output: "Agent crashed" });
  }

  // Synthesize: feed all agent outputs to the orchestrator.
  const combined = agentResults
    .map((a) => `### ${a.name.toUpperCase()} AGENT\n${a.output}`)
    .join("\n\n");

  let answer = "";
  let verdict: string | undefined;
  let confidence: number | undefined;
  try {
    const synth = await runAgent(provider, ORCHESTRATOR_PROMPT(ctx), combined, { maxIterations: 4 });
    answer = synth.answer;
    // Try to extract verdict + confidence from the report.
    const vMatch = answer.match(/\b(BULLISH|BEARISH|NEUTRAL|HOLD)\b/i);
    if (vMatch) verdict = vMatch[1].toLowerCase();
    const cMatch = answer.match(/(\d{1,3})\s*%?\s*confidence/i);
    if (cMatch) confidence = Math.min(100, Math.max(0, parseInt(cMatch[1], 10))) / 100;
  } catch (err) {
    answer = `Synthesis failed: ${err instanceof Error ? err.message : String(err)}`;
  }

  await prisma.researchReport.update({
    where: { id: report.id },
    data: { status: "done", summary: answer, verdict: verdict || null, confidence: confidence ?? null },
  });

  return {
    reportId: report.id,
    answer,
    verdict,
    confidence,
    agents: agentResults.map((a) => ({ name: a.name, status: a.status, toolCalls: a.toolCalls, toolErrors: a.toolErrors })),
  };
}

// Re-export getTool for convenience.
export { getTool };
