import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// Regression guard: the floating Assistant (ChatDock) MUST expose the model
// selector and send the chosen model per turn.
//
// It previously rendered a read-only model pill and never passed a model to the
// run, so the always-on assistant was stuck on whatever model Settings last
// saved — the ChatBot tab and bot chats had a working picker, the dock did not
// (the original "can't change the AI model on our assistant" bug). No React
// testing library is installed (the vitest environment is `node`; see
// vitest.config.ts), so this asserts the wiring points at the source level, the
// same pattern the other chat-surface guards use. Removing any of them fails
// here instead of silently shipping a dead control.

const SOURCE = readFileSync(fileURLToPath(new URL('./chat-dock.tsx', import.meta.url)), 'utf8');

describe('ChatDock model selection', () => {
  it('uses the shared composer model state', () => {
    expect(SOURCE).toMatch(/useChatModel\(\)/);
  });

  it('renders the shared ModelSelector wired to that state', () => {
    expect(SOURCE).toMatch(/<ModelSelector\s+state=\{chatModel\}/);
  });

  it('sends the selected model and effort on every run', () => {
    expect(SOURCE).toMatch(/model:\s*chatModel\.displayModel/);
    expect(SOURCE).toMatch(/reasoningEffort:\s*reasoningEffort\.effort/);
  });

  it('renders the shared reasoning-effort control (ChatBot parity)', () => {
    expect(SOURCE).toMatch(/useReasoningEffort\(\)/);
    expect(SOURCE).toMatch(/<EffortControl\b/);
  });

  it('no longer renders a read-only model label', () => {
    // The old pill echoed the last-answered model with no way to change it.
    expect(SOURCE).not.toContain('activeModel ?? providerLabel');
  });
});
