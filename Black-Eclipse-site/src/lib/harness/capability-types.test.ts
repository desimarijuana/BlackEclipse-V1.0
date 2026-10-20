import { describe, expect, it } from 'vitest';

import { coerceCapabilityBuild, mergeCapabilityBuild } from './capability-types';

describe('capability build view', () => {
  it('coerces the runtime payload and keeps only declared statuses', () => {
    expect(coerceCapabilityBuild({ capabilityId: 'x', status: 'not-a-status' })).toBeUndefined();
    expect(coerceCapabilityBuild({ capabilityId: 'x', status: 'active' })?.status).toBe('active');
  });

  it('merges a build onto the request without losing the need', () => {
    const requested = mergeCapabilityBuild(undefined, {
      capabilityId: 'ulcer_index',
      need: 'Compute the Ulcer Index',
      status: 'gap',
      surface: 'capability_builder',
      steps: ['write it'],
    }, 'requested');
    const built = mergeCapabilityBuild(requested, {
      capabilityId: 'ulcer_index',
      version: '1.0.0',
      status: 'active',
      testStatus: 'verified',
      verification: {
        status: 'verified', ok: true,
        checks: [{ name: 'sandbox-run', ok: true, detail: 'ok' }],
        failed: [], stderr: '',
      },
    }, 'built');
    expect(built).toMatchObject({
      capabilityId: 'ulcer_index',
      need: 'Compute the Ulcer Index',
      version: '1.0.0',
      status: 'active',
      steps: ['write it'],
      testStatus: 'verified',
    });
  });

  it('maps a verification failure to unverified and keeps the checks', () => {
    const built = mergeCapabilityBuild(undefined, {
      capabilityId: 'x', need: 'x', status: 'active',
      verification: { status: 'verified', ok: true, checks: [{ name: 'a', ok: true, detail: '' }], failed: [], stderr: '' },
    }, 'built');
    const failed = mergeCapabilityBuild(built, {
      capabilityId: 'x',
      verification: { status: 'failed', ok: false, checks: [{ name: 'a', ok: false, detail: 'bad' }], failed: [{ name: 'a', ok: false, detail: 'bad' }], stderr: 'bad' },
    }, 'verification_failed');
    expect(failed?.status).toBe('unverified');
    expect(failed?.verification?.failed).toHaveLength(1);
  });

  it('ignores a malformed later event and keeps the current view', () => {
    const current = mergeCapabilityBuild(undefined, { capabilityId: 'x', need: 'x', status: 'gap' }, 'requested');
    expect(mergeCapabilityBuild(current, {}, 'built')).toBe(current);
  });

  it('coerces an effectful hand-off without inventing a verification', () => {
    const view = coerceCapabilityBuild({
      capabilityId: 'weekly_review',
      need: 'prepare a weekly review',
      status: 'handoff_required',
      surface: 'skill_create',
      nextTool: 'skill_create',
      steps: ['the SkillManifest validates'],
      missing: ["the skill's instructions"],
    });
    expect(view?.status).toBe('handoff_required');
    expect(view?.nextTool).toBe('skill_create');
    expect(view?.verification).toBeUndefined();
    expect(view?.steps).toEqual(['the SkillManifest validates']);
    expect(view?.missing).toEqual(["the skill's instructions"]);
  });
});
