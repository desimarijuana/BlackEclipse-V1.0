import { describe, expect, it } from 'vitest';
import { buildMemoryRunView } from './memory-action';

describe('buildMemoryRunView', () => {
  it('returns null for absent/non-object input', () => {
    expect(buildMemoryRunView(undefined)).toBeNull();
    expect(buildMemoryRunView(null)).toBeNull();
    expect(buildMemoryRunView('nope')).toBeNull();
    expect(buildMemoryRunView([])).toBeNull();
    expect(buildMemoryRunView({})).toBeNull();
  });

  it('maps a saved action with inspect + undo', () => {
    const view = buildMemoryRunView({
      action: 'saved',
      contentPreview: 'User prefers terse answers',
      memoryType: 'preference',
      scope: 'user',
      inspectPath: '/api/eclipse-memory/memories/mem_1',
      undoPath: '/api/eclipse-memory/memories/mem_1/archive',
    });
    expect(view?.action?.kind).toBe('saved');
    expect(view?.action?.headline).toBe('Remembered');
    expect(view?.action?.inspectPath).toContain('mem_1');
    expect(view?.action?.undoPath).toContain('archive');
  });

  it('maps a refusal honestly (no inspect link)', () => {
    const view = buildMemoryRunView({ action: 'refused', reason: 'looks like a secret' });
    expect(view?.action?.kind).toBe('refused');
    expect(view?.action?.headline).toBe('Not saved');
    expect(view?.action?.reason).toContain('secret');
    expect(view?.action?.inspectPath).toBeUndefined();
  });

  it('maps needs_confirmation without a save', () => {
    const view = buildMemoryRunView({ action: 'needs_confirmation', reason: 'sensitive' });
    expect(view?.action?.kind).toBe('needs_confirmation');
  });

  it('maps a conflict as needs_review, never as saved', () => {
    const view = buildMemoryRunView({
      action: 'needs_review',
      contentPreview: 'I prefer detailed answers',
      memoryType: 'preference',
      reason: 'This conflicts with an existing memory',
      inspectPath: '/api/eclipse-memory/memories/mem_2',
    });
    expect(view?.action?.kind).toBe('needs_review');
    expect(view?.action?.headline).toContain('conflicts');
    expect(view?.action?.headline).not.toBe('Remembered');
    expect(view?.action?.inspectPath).toContain('mem_2');
  });

  it('maps a suggested outcome as NOT saved, with the suggestion path', () => {
    const view = buildMemoryRunView({
      action: 'suggested',
      suggestionId: 'sugg_1',
      suggestionContent: 'I prefer concise answers',
      suggestionType: 'preference',
      suggestionScope: 'user',
      suggestionPath: '/api/eclipse-memory/suggestions',
      reason: 'possible durable preference',
    });
    expect(view?.action?.kind).toBe('suggested');
    expect(view?.action?.headline).toContain('Not saved');
    expect(view?.action?.suggestionId).toBe('sugg_1');
    expect(view?.action?.suggestionPath).toBe('/api/eclipse-memory/suggestions');
    expect(view?.action?.inspectPath).toBeUndefined();
  });

  it('maps a full-storage outcome truthfully (not saved)', () => {
    const view = buildMemoryRunView({ action: 'memory_full', reason: 'memory is full (50/50 active)' });
    expect(view?.action?.kind).toBe('memory_full');
    expect(view?.action?.headline).toContain('full');
    expect(view?.action?.inspectPath).toBeUndefined();
  });

  it('maps an ambiguous forget/correct as needing clarification', () => {
    const view = buildMemoryRunView({ action: 'needs_clarification', reason: 'more than one memory matches' });
    expect(view?.action?.kind).toBe('needs_clarification');
  });

  it('surfaces learning eligibility and always provides the queue path', () => {
    const view = buildMemoryRunView({
      learningEligibility: { eligible: false, reason: 'no tool use', learnQueuePath: '/?tab=skills&sub=skills.learning' },
    });
    expect(view?.eligibility?.eligible).toBe(false);
    expect(view?.eligibility?.learnQueuePath).toBe('/?tab=skills&sub=skills.learning');
    expect(view?.eligibility?.autoCaptured).toBe(false);
  });

  it('surfaces automatic capture with the created-candidate count', () => {
    const view = buildMemoryRunView({
      learningEligibility: { eligible: true, reason: 'automatically captured a reusable lesson', autoCaptured: true },
      learningAnalysis: { candidatesCreated: 2 },
    });
    expect(view?.eligibility?.autoCaptured).toBe(true);
    expect(view?.eligibility?.candidatesCreated).toBe(2);
  });

  it('defaults the queue path when the backend omits it', () => {
    const view = buildMemoryRunView({ learningEligibility: { eligible: true, reason: 'multi-step' } });
    expect(view?.eligibility?.learnQueuePath).toBe('/?tab=skills&sub=skills.learning');
  });

  it('surfaces an explicit skill draft as ready (not a prompt)', () => {
    const view = buildMemoryRunView({
      action: 'skill_requested',
      learningEligibility: { eligible: true, reason: 'the user asked', skillRequested: true, skillDraftReady: true },
    });
    expect(view?.eligibility?.skillDraftReady).toBe(true);
    expect(view?.eligibility?.autoCaptured).toBe(false);
  });

  it('combines an action and eligibility', () => {
    const view = buildMemoryRunView({
      action: 'skill_requested',
      learningEligibility: { eligible: true, reason: 'the user asked', skillRequested: true },
    });
    expect(view?.action?.kind).toBe('skill_requested');
    expect(view?.eligibility?.skillRequested).toBe(true);
    expect(view?.eligibility?.skillDraftReady).toBe(false);
  });

  it('ignores unknown action names', () => {
    const view = buildMemoryRunView({ action: 'something_new' });
    expect(view).toBeNull();
  });
});
