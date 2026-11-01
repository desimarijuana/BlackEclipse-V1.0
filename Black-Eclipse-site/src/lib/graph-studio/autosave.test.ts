import { describe, expect, it } from 'vitest';
import { AUTO_SAVE_DELAY_MS, shouldAutoSave } from './autosave';

const base = {
  enabled: true,
  dirty: true,
  busy: false,
  errors: 0,
  hasWorkflow: true,
  hasIr: true,
  changed: true,
};

describe('auto-save policy', () => {
  it('saves only when the document is dirty and valid', () => {
    expect(shouldAutoSave(base)).toBe(true);
    expect(shouldAutoSave({ ...base, dirty: false })).toBe(false);
    expect(shouldAutoSave({ ...base, errors: 1 })).toBe(false);
  });

  it('never writes a version whose content is unchanged', () => {
    // Opening the editor can dispatch a no-op layout patch; dirty is true but
    // the hash still matches the saved version.
    expect(shouldAutoSave({ ...base, changed: false })).toBe(false);
  });

  it('never overlaps a save already in flight', () => {
    expect(shouldAutoSave({ ...base, busy: true })).toBe(false);
  });

  it('respects the operator toggle', () => {
    expect(shouldAutoSave({ ...base, enabled: false })).toBe(false);
  });

  it('needs a persisted workflow and a document', () => {
    expect(shouldAutoSave({ ...base, hasWorkflow: false })).toBe(false);
    expect(shouldAutoSave({ ...base, hasIr: false })).toBe(false);
  });

  it('waits long enough to coalesce typing', () => {
    expect(AUTO_SAVE_DELAY_MS).toBeGreaterThanOrEqual(1_000);
    expect(AUTO_SAVE_DELAY_MS).toBeLessThanOrEqual(5_000);
  });
});
