import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// The composer effort control ("model intelligence") must be REACHABLE, not just
// present: a copy-only test over dead code stays green forever. This asserts the
// full path a per-question effort takes from the composer to the runtime's run
// payload, by reading the real sources (no React testing library is installed —
// the vitest include only matches `.test.ts`).

function source(rel: string): string {
  const here = fileURLToPath(new URL(rel, import.meta.url));
  return readFileSync(here, 'utf8');
}

describe('composer effort control wiring', () => {
  it('mounts the control in ChatInput behind the effortState prop', () => {
    const input = source('./chat-input.tsx');
    expect(input).toContain("from './effort-control'");
    expect(input).toContain('effortState');
    expect(input).toContain('<EffortControl');
  });

  it('renders the control from the shared reasoning vocabulary', () => {
    const control = source('./effort-control.tsx');
    expect(control).toContain('EFFORT_STOPS');
    expect(control).toContain('@base-ui/react/slider');
    expect(control).toContain('@/lib/agent/reasoning');
  });

  it('skins the control with theme tokens, not a foreign palette', () => {
    const control = source('./effort-control.tsx');
    expect(control).toContain('text-primary');
    expect(control).toContain('border-border/40');
    // The old off-theme violet/sky palette is gone.
    expect(control).not.toMatch(/violet-\d/);
    expect(control).not.toMatch(/sky-\d|fuchsia-\d/);
  });

  it('animates the top (Ultra) thumb and stays reduced-motion safe', () => {
    const control = source('./effort-control.tsx');
    expect(control).toContain('effort-ultra-glow');
    expect(control).toContain('effort-ultra-shock');
    expect(control).toContain('effort-ultra-plasma');
    expect(control).toContain('effort-ultra-core');
    // The animation is defined once in globals.css and disabled globally by the
    // prefers-reduced-motion rule.
    const css = source('../../app/globals.css');
    expect(css).toContain('effortUltraGlow');
    expect(css).toContain('effortUltraShock');
    expect(css).toContain('effortUltraSpin');
    expect(css).toContain('prefers-reduced-motion');
  });

  it('uses the accent color for the brain and a laser-beam sweep on Ultra', () => {
    const control = source('./effort-control.tsx');
    // The brain is solid and painted with a DEDICATED accent class — not
    // `text-primary`, which a global CSS remap forces to muted gray (its `.dark`
    // variant out-specifies the `svg.text-primary` green rule, so an icon that
    // relied on it rendered gray — the "animation looks dead" bug).
    expect(control).toContain('weight="fill"');
    expect(control).toContain('effort-accent');
    expect(control).not.toMatch(/className="text-primary/);
    const css = source('../../app/globals.css');
    expect(css).toContain('.effort-accent');
    expect(css).toMatch(/\.effort-accent[^{]*\{[^}]*color:\s*var\(--primary\)/);
    // The Ultra fill (and the persistent pill) carry a laser beam that sweeps.
    expect(control).toContain('effort-ultra-beam');
    expect(css).toContain('effortUltraBeam');
  });

  it('shows the energy beam on the persistent pill, not only the popover', () => {
    // The popover closes the moment a level is picked, so an effect that only
    // lives inside it is invisible at rest — the reported "animation not working".
    const control = source('./effort-control.tsx');
    const triggerIdx = control.indexOf('PopoverPrimitive.Trigger');
    const beamIdx = control.indexOf('effort-ultra-beam');
    expect(triggerIdx).toBeGreaterThan(-1);
    expect(beamIdx).toBeGreaterThan(triggerIdx);
    // The shared energy core is used by the thumb.
    expect(control).toContain('function EnergyCore');
    expect(control).toContain('<EnergyCore');
  });

  it('passes the per-question effort from the chat surface to the run hook', () => {
    const chat = source('../screens/stock-chat.tsx');
    expect(chat).toContain('useReasoningEffort');
    expect(chat).toContain('effortState={reasoningEffort}');
    // The chosen effort is sent with the turn (only meaningful value; Auto sends undefined).
    expect(chat).toMatch(/reasoningEffort:\s*reasoningEffort\.effort/);
  });
});

describe('per-question effort transport', () => {
  it('forwards reasoningEffort from the composer through the provider payload', () => {
    const registry = source('../../lib/agent/registry.ts');
    expect(registry).toContain('reasoningEffort: options?.reasoningEffort');
    const hook = source('../../lib/agent/use-agent-run.ts');
    expect(hook).toContain('reasoningEffort: args.reasoningEffort');
  });

  it('honours the override on both chat front doors', () => {
    for (const rel of [
      '../../app/api/harness/chat/route.ts',
      '../../app/api/harness/chat/stream/route.ts',
    ]) {
      const route = source(rel);
      expect(route).toContain('isReasoningLevel');
      expect(route).toContain('reasoningEffort');
    }
  });

  it('takes the override from the composer hook, persisted per client', () => {
    const store = source('../../lib/agent/use-reasoning-effort.ts');
    expect(store).toContain('be_reasoning_effort_v1');
    expect(store).toContain('isReasoningLevel');
  });
});
