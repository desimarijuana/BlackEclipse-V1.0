import type { AgentProvider, ChatMessage } from './types';

/**
 * Built-in mock provider. Used when no real LLM provider is configured.
 * Returns canned, finance-flavored responses so the UI is fully functional
 * out of the box.
 */
export class MockProvider implements AgentProvider {
  readonly id = 'mock';
  readonly label = 'Mock (built-in)';

  isConfigured(): boolean {
    return true;
  }

  async chat(messages: ChatMessage[]): Promise<string> {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
    const query = lastUser?.content ?? '';

    // Simple keyword-based responses to feel "agentic" without an LLM.
    if (/analy|research|report/i.test(query)) {
      return `Performing autonomous AI intelligence scan... Analyzing P/E ratios, services revenue growth, and news sentiments. Technical indicators suggest immediate support thresholds are holding firmly, showing positive consolidation.`;
    }
    if (/sentiment|outlook|news/i.test(query)) {
      return `Market sentiment is classified as BULLISH with an estimated positive impact. This shifts technical weights toward short-term momentum flags in related industry groups.`;
    }
    if (/portfolio|holding|position/i.test(query)) {
      return `Reviewing your portfolio... Diversification looks healthy. Consider rebalancing toward higher-conviction positions and maintaining strict risk control limits.`;
    }
    return `Analyzing stock data for your request: "${query}". Market conditions suggest strong momentum in the tech sector today. NVDA and AAPL are showing strong accumulation, while TSLA has consolidated support near $175.`;
  }
}
