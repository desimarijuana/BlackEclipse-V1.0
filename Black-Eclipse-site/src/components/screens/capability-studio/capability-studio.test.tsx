// ─── Capability Studio tests (Phase D) ──────────────────────────────────────
// The vitest environment is `node` (no DOM), so — like the canvas/response
// tests — the studio renders with `react-dom/server`. What matters here: the
// surface is ONE navigable place (the section switcher exposes pages &
// widgets, tools & plugins, skills and integrations), an inactive section
// renders nothing visible, and the summary derivations are honest — an
// untested connection is never counted as failing, an unknown completeness
// never counted as healthy.

import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

import { CapabilityStudioScreen } from './capability-studio-screen';
import { summarizeSkills } from './skills-section';
import { summarizeConnectors } from './integrations-section';
import type { SkillListResult } from '@/lib/harness/skills-browser';
import type { SkillSummary } from '@/lib/harness/skills-types';

function skill(overrides: Partial<SkillSummary>): SkillSummary {
  return {
    id: 'skill.x',
    name: 'Skill X',
    version: '1.0.0',
    description: '',
    category: 'research',
    tags: [],
    status: 'draft',
    riskLevel: 'low',
    permissions: [],
    requiredTools: [],
    evaluationStatus: 'not_evaluated',
    ...overrides,
  };
}

function listResult(skills: SkillSummary[], extra: Partial<SkillListResult> = {}): SkillListResult {
  return {
    skills,
    loadErrors: [],
    duplicates: [],
    projectNotices: [],
    projectDrift: false,
    shadowed: [],
    contentFindings: {},
    quarantined: [],
    ...extra,
  };
}

describe('summarizeSkills', () => {
  it('counts live, pending and attention skills from the real registry fields', () => {
    const counts = summarizeSkills(
      listResult([
        skill({ id: 'a', status: 'active', evaluationStatus: 'passed' }),
        skill({ id: 'b', status: 'enabled', evaluationStatus: 'passed' }),
        skill({ id: 'c', status: 'draft', evaluationStatus: 'not_evaluated' }),
        skill({ id: 'd', status: 'evaluating', evaluationStatus: 'needs_review' }),
        skill({ id: 'e', status: 'rejected', evaluationStatus: 'failed' }),
      ]),
    );
    expect(counts).toEqual({ total: 5, enabled: 2, pending: 2, issues: 1 });
  });

  it('treats registry-level problems (load errors, quarantines, duplicates) as attention', () => {
    const counts = summarizeSkills(
      listResult([skill({})], { loadErrors: ['bad.md: parse failed'], quarantined: ['evil'], duplicates: ['dup'] }),
    );
    expect(counts.issues).toBe(3);
  });
});

describe('summarizeConnectors', () => {
  const connector = (over: Partial<Parameters<typeof summarizeConnectors>[0][number]> = {}) => ({
    id: 'c1',
    name: 'Connector',
    enabled: true,
    capabilities: ['CUSTOM_DATASET'],
    health: { state: 'CONNECTED' },
    ...over,
  });

  it('counts enabled connectors and flags only RECORDED failing states', () => {
    const counts = summarizeConnectors([
      connector(),
      connector({ id: 'c2', health: { state: 'ERROR' } }),
      // Never tested: not an incident, not counted as failing.
      connector({ id: 'c3', health: { state: 'UNKNOWN' } }),
      connector({ id: 'c4', health: {} }),
      // Disabled: not shipping traffic, so its old error is not attention.
      connector({ id: 'c5', enabled: false, health: { state: 'ERROR' } }),
    ]);
    expect(counts).toEqual({ total: 5, enabled: 4, attention: 1 });
  });
});

describe('CapabilityStudioScreen', () => {
  it('renders one navigable surface with every capability section', () => {
    const html = renderToStaticMarkup(<CapabilityStudioScreen />);
    expect(html).toContain('Capability Studio');
    expect(html).toContain('Pages &amp; widgets');
    expect(html).toContain('Tools &amp; plugins');
    expect(html).toContain('Skills');
    expect(html).toContain('Integrations');
    // The default section is the embedded builder (its own chrome is hidden).
    expect(html).toContain('New page');
    expect(html).not.toContain('>UI Builder</h1>');
  });

  it('renders the plugins section on demand with the honest install hint', () => {
    const html = renderToStaticMarkup(<CapabilityStudioScreen initialSection="plugins" />);
    expect(html).toContain('Plugins');
    expect(html).toContain('operator acquisition route');
  });

  it('renders the skills section in its loading state without fabricating counts', () => {
    const html = renderToStaticMarkup(<CapabilityStudioScreen initialSection="skills" />);
    expect(html).toContain('Loading…');
    expect(html).not.toContain('Awaiting evaluation');
  });

  it('renders the integrations section in its loading state', () => {
    const html = renderToStaticMarkup(<CapabilityStudioScreen initialSection="integrations" />);
    expect(html).toContain('Loading…');
    expect(html).not.toContain('Connected data sources');
  });
});
