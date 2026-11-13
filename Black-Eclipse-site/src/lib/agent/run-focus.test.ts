import { describe, expect, it } from 'vitest';
import { bindRunChat, setFocusedChat, shouldIngestRun, unbindRunChat } from './run-focus';

describe('run focus (parallel conversations share one workspace)', () => {
  it('only ingests the focused conversation run', () => {
    bindRunChat('run_a', 'chat_a');
    bindRunChat('run_b', 'chat_b');
    setFocusedChat('chat_a');
    expect(shouldIngestRun('run_a')).toBe(true);
    expect(shouldIngestRun('run_b')).toBe(false);
    // An untagged frame is allowed rather than silently dropped.
    expect(shouldIngestRun(undefined)).toBe(true);
    expect(shouldIngestRun('run_untagged')).toBe(true);
    unbindRunChat('run_a');
    unbindRunChat('run_b');
  });
});
