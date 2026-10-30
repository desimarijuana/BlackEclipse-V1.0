import { describe, expect, it } from 'vitest';
import { describeVoiceEngine } from './types';

describe('describeVoiceEngine', () => {
  it('prefers Whisper when the server is ready in auto mode', () => {
    expect(describeVoiceEngine('auto', true, true)).toBe('whisper');
  });

  it('falls back to the browser when no provider is configured', () => {
    expect(describeVoiceEngine('auto', false, true)).toBe('browser');
  });

  it('reports unavailable when neither engine exists', () => {
    expect(describeVoiceEngine('auto', false, false)).toBe('none');
  });

  it('never silently switches away from an explicit choice', () => {
    expect(describeVoiceEngine('whisper', false, true)).toBe('none');
    expect(describeVoiceEngine('browser', true, false)).toBe('none');
  });
});
