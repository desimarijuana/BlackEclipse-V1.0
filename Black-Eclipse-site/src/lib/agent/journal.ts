// ── Journal Agent — the Agentic Journal orchestrator ─────────────────────────
// Runs an LLM with the journal tools to interpret the trader's real data.
// The AI interprets deterministic analytics — it never fabricates numbers.
//
// Flow:
//   1. Detect intent from the query (trade review / performance / strategy /
//      psychology / weekly / monthly / general).
//   2. Run the LLM with the journal tool set so it can pull real data.
//   3. Return the AI interpretation grounded in computed statistics.

import { OpenAICompatibleProvider } from "./openai-provider";
import { getJournalTool, journalToolSchemas } from "./journal-tools";
import type { ToolCall } from "./loop";

export interface JournalAgentRequest {
  query: string;
  tradeId?: string;
  start?: string;
  end?: string;
}

export interface JournalAgentResult {
  answer: string;
  toolCalls: number;
  toolErrors: number;
}

type Intent =
  | "trade_review"
  | "performance"
  | "strategy"
  | "psychology"
  | "weekly"
  | "monthly"
  | "general";

function detectIntent(query: string, req: JournalAgentRequest): Intent {
  const q = query.toLowerCase();
  if (req.tradeId || /review this trade|trade review|this trade|review trade/i.test(q)) return "trade_review";
  if (/weekly|this week|last week/i.test(q)) return "weekly";
  if (/monthly|wrapped|this month|last month/i.test(q)) return "monthly";
  if (/strategy|setup|playbook/i.test(q)) return "strategy";
  if (/psychology|emotion|behavior|confidence|discipline/i.test(q)) return "psychology";
  if (/performance|summary|how am i|overall|stats|win rate|profit/i.test(q)) return "performance";
  return "general";
}

const SYSTEM_PROMPTS: Record<Intent, string> = {
  trade_review:
    `You are the TRADE REVIEW agent for BlackEclipse. Review a specific trade using the get_trade_review tool. ` +
    `Give a verdict (good trade / bad trade / neutral), what went well, any concerns, and how it compares to similar historical trades. ` +
    `Reference the real numbers from the tool output. Be honest and specific. Do not fabricate statistics.`,
  performance:
    `You are the PERFORMANCE ANALYST for BlackEclipse. Use get_journal_summary to pull the trader's real performance; ` +
    `when the user asks specifically about broker results, use get_broker_performance and get_broker_status. ` +
    `Never mix broker-sourced and manual/demo trades without saying which is which. ` +
    `Interpret the numbers: what's working, what's leaking money, and what to improve. Reference actual figures. Do not fabricate statistics.`,
  strategy:
    `You are the STRATEGY ANALYST for BlackEclipse. Use get_strategy_analysis to pull real performance by setup. ` +
    `Identify which setups work best, which are weak, and recommend where to focus. Reference actual figures. Do not fabricate statistics.`,
  psychology:
    `You are the PSYCHOLOGY ANALYST for BlackEclipse. Use get_psychology to pull real behavioral data. ` +
    `Interpret emotional patterns, confidence correlation, and the biggest behavioral leaks. Reference actual figures. Do not fabricate statistics.`,
  weekly:
    `You are the WEEKLY REVIEW agent for BlackEclipse. Use get_weekly_review to pull the deterministic weekly review. ` +
    `Interpret what worked, what hurt, and the biggest leak. Give actionable advice for next week. Reference actual figures. Do not fabricate statistics.`,
  monthly:
    `You are the MONTHLY WRAPPED agent for BlackEclipse. Use get_monthly_wrapped to pull the real monthly report. ` +
    `Summarize the month's performance and highlight the best setup, best market, and biggest leak. Reference actual figures. Do not fabricate statistics.`,
  general:
    `You are the JOURNAL AGENT for BlackEclipse. Answer the user's question about their trading history using the journal tools ` +
    `(get_journal_summary, get_trade_review, get_weekly_review, get_strategy_analysis, get_psychology, get_monthly_wrapped, get_broker_status, get_broker_performance). ` +
    `Always ground your answer in the real data the tools return. If a tool isn't relevant, say so. Do not fabricate statistics.`,
};

/** Run the journal agent loop with the journal tool set. */
export async function runJournalAgent(req: JournalAgentRequest): Promise<JournalAgentResult> {
  const provider = new OpenAICompatibleProvider();
  const intent = detectIntent(req.query, req);
  const systemPrompt = SYSTEM_PROMPTS[intent];

  // Build a user query that includes any explicit context (trade id, dates).
  let userQuery = req.query;
  if (req.tradeId) userQuery += `\n\nTrade id to review: ${req.tradeId}`;
  if (req.start && req.end) userQuery += `\n\nDate range: ${req.start} to ${req.end}`;

  const messages: { role: "system" | "user" | "assistant" | "tool"; content: string; toolCalls?: ToolCall[]; toolCallId?: string }[] = [
    { role: "system", content: systemPrompt },
    { role: "user", content: userQuery },
  ];

  let toolCalls = 0;
  let toolErrors = 0;
  const maxIterations = 8;

  for (let i = 0; i < maxIterations; i++) {
    const response = await provider.chat(messages, journalToolSchemas());

    if (!response.toolCalls || response.toolCalls.length === 0) {
      return { answer: response.content, toolCalls, toolErrors };
    }

    messages.push({ role: "assistant", content: response.content || "", toolCalls: response.toolCalls });

    for (const call of response.toolCalls) {
      toolCalls++;
      const tool = getJournalTool(call.name);
      let result: string;
      try {
        if (!tool) {
          result = `Unknown tool "${call.name}". Available: ${journalToolSchemas().map((t) => t.function.name).join(", ")}`;
          toolErrors++;
        } else {
          result = await tool.execute(call.arguments || {});
        }
      } catch (err) {
        result = `Tool error: ${err instanceof Error ? err.message : String(err)}`;
        toolErrors++;
      }
      messages.push({ role: "tool", content: result, toolCallId: call.id });
    }
  }

  return {
    answer: "Reached max iterations without a final answer. Please try a more specific question.",
    toolCalls,
    toolErrors,
  };
}
