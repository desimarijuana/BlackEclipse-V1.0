import { describe, it, expect } from 'vitest';
import { buildAgentInstruction } from '@/lib/harness/commands/command-agent';
import { ANATOMY_EXAMPLE_PROMPTS } from './prompts';

// Every advertised /anatomy prompt must route to the agent.anatomy directive and
// carry the guidance that makes the figure validate (the schema read-back and the
// one `eclipse-response` fence). This is the deterministic half of the anatomy
// prompt suite; the rendering half is `scene.test.ts` + `anatomy-render.test.tsx`.
describe('anatomy example prompts', () => {
  it('advertises a non-trivial list', () => {
    expect(ANATOMY_EXAMPLE_PROMPTS.length).toBeGreaterThanOrEqual(6);
  });

  for (const prompt of ANATOMY_EXAMPLE_PROMPTS) {
    it(`"${prompt}" routes to an isometric-figure directive`, () => {
      const cmd = buildAgentInstruction(prompt);
      expect(cmd, 'has an agent directive').toBeTruthy();
      expect(cmd!.command).toBe('anatomy');
      expect(cmd!.instruction).toContain('anatomy');
      expect(cmd!.instruction).toContain('response_block_schema');
      expect(cmd!.instruction).toContain('eclipse-response');
    });
  }

  it('asks what to illustrate when no subject is given', () => {
    const cmd = buildAgentInstruction('/anatomy');
    expect(cmd?.command).toBe('anatomy');
    expect(cmd?.instruction).toMatch(/ask the user/i);
  });
});
