import { describe, expect, it } from 'vitest';
import type { ResponseStatus } from '@/lib/agent/response-model';
import type { HarnessUiEvent } from '@/lib/agent/events';
import { moodFromEvent, moodFromStatus } from './ghost-mood';

describe('moodFromStatus', () => {
  it('maps the working lifecycle to a face', () => {
    const cases: Record<ResponseStatus, string> = {
      queued: 'thinking',
      planning: 'thinking',
      tool_running: 'working',
      streaming: 'speaking',
      awaiting_approval: 'waiting',
      completed: 'happy',
      error: 'sad',
      cancelled: 'sad',
    };
    for (const [status, mood] of Object.entries(cases)) {
      expect(moodFromStatus(status as ResponseStatus)).toBe(mood);
    }
  });
});

describe('moodFromEvent', () => {
  it('maps activity start to working and deltas to speaking', () => {
    const start: HarnessUiEvent = {
      kind: 'activity_start',
      item: { id: 't', kind: 'tool', name: 'x', label: 'Using x', status: 'running' },
    };
    expect(moodFromEvent(start)).toBe('working');
    expect(moodFromEvent({ kind: 'delta', text: 'hi' })).toBe('speaking');
  });

  it('maps a final to happy or sad by its error', () => {
    expect(moodFromEvent({ kind: 'final' })).toBe('happy');
    expect(moodFromEvent({ kind: 'final', error: 'boom' })).toBe('sad');
    expect(moodFromEvent({ kind: 'error', message: 'boom' })).toBe('sad');
  });

  it('maps an approval request to waiting', () => {
    expect(moodFromEvent({ kind: 'approval_request', approval: { id: 'a', kind: 'tool', title: 'Approve' } })).toBe(
      'waiting',
    );
  });

  it('returns null for events that must not move the face', () => {
    expect(moodFromEvent({ kind: 'changes', items: [] })).toBeNull();
    expect(moodFromEvent({ kind: 'approval_resolved', approved: true })).toBeNull();
  });
});
