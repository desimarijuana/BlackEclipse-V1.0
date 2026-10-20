import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

import { CapabilityCard } from './capability-card';

const active = {
  requestId: 'capreq_1',
  capabilityId: 'ulcer_index',
  version: '1.0.0',
  need: 'Compute the Ulcer Index',
  kind: 'recipe',
  surface: 'capability_builder',
  scope: 'workspace',
  status: 'active',
  tests: ['test_capability.py'],
  testStatus: 'verified',
  verification: {
    status: 'verified',
    ok: true,
    checks: [
      { name: 'manifest-policy', ok: true, detail: 'ok' },
      { name: 'sandbox-run', ok: true, detail: 'ok' },
    ],
    failed: [],
    stderr: '',
  },
};

describe('CapabilityCard', () => {
  it('shows the active build with its pass count', () => {
    const html = renderToStaticMarkup(<CapabilityCard view={active} />);
    expect(html).toContain('Built, tested, and active');
    expect(html).toContain('ulcer_index');
    expect(html).toContain('2 of 2 checks passed');
    expect(html).toContain('Analysis recipe');
  });

  it('shows an unverified build honestly', () => {
    const html = renderToStaticMarkup(<CapabilityCard view={{
      ...active,
      status: 'unverified',
      testStatus: 'failed',
      verification: {
        status: 'failed',
        ok: false,
        checks: [{ name: 'sandbox-run', ok: false, detail: 'failed' }],
        failed: [{ name: 'sandbox-run', ok: false, detail: 'failed' }],
        stderr: 'AssertionError',
      },
    }} />);
    expect(html).toContain('Built, but not verified');
    expect(html).toContain('Contract test failed');
  });

  it('shows a one-off route instead of pretending a capability exists', () => {
    const html = renderToStaticMarkup(<CapabilityCard view={{
      need: 'Compute the Ulcer Index', status: 'one_off', surface: 'analysis_run',
    }} />);
    expect(html).toContain('One-off computation');
    expect(html).not.toContain('Built, tested, and active');
  });

  it('renders nothing for a malformed view', () => {
    expect(renderToStaticMarkup(<CapabilityCard view={{}} />)).toBe('');
  });

  it('offers the build actions when the runtime proposed a capability', () => {
    const html = renderToStaticMarkup(
      <CapabilityCard
        view={{
          need: 'Compute the Ulcer Index',
          status: 'gap',
          surface: 'capability_builder',
          steps: ['write the recipe', 'run the contract test'],
        }}
        onFollowup={() => {}}
      />,
    );
    expect(html).toContain('Build it');
    expect(html).toContain('Show plan');
    expect(html).toContain('Not now');
  });

  it('hides actions when there is no follow-up sink', () => {
    const html = renderToStaticMarkup(
      <CapabilityCard view={{ need: 'Compute the Ulcer Index', status: 'gap' }} />,
    );
    expect(html).not.toContain('Build it');
  });

  it('offers the hand-off continue action with the owner tool', () => {
    const html = renderToStaticMarkup(
      <CapabilityCard
        view={{
          capabilityId: 'private_ledger_tool',
          need: 'build a tool for my private ledger',
          status: 'handoff_required',
          surface: 'scaffold_kit',
          nextTool: 'scaffold_kit',
        }}
        onFollowup={() => {}}
      />,
    );
    expect(html).toContain('Continue');
    expect(html).toContain('scaffold_kit');
  });

  it('offers the RSL rebuild action for an unverified capability', () => {
    const html = renderToStaticMarkup(
      <CapabilityCard
        view={{ ...active, status: 'unverified', testStatus: 'failed' }}
        onFollowup={() => {}}
      />,
    );
    expect(html).toContain('Rebuild with RSL');
  });
});
