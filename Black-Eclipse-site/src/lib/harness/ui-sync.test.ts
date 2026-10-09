import { beforeEach, describe, expect, it, vi } from 'vitest';

const registerComponent = vi.hoisted(() => vi.fn(async () => ({})));

vi.mock('@/lib/harness/ui-client', () => ({ registerComponent }));
vi.mock('@/lib/ui-engineering/registry-catalog', () => ({
  dashboardComponentSpecs: () => [{ id: 'a' }, { id: 'b' }],
}));

import { syncCoreCatalog } from './ui-sync';

describe('syncCoreCatalog', () => {
  beforeEach(() => registerComponent.mockReset());

  it('registers every spec and counts failures', async () => {
    registerComponent.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('runtime down'));
    const result = await syncCoreCatalog(true);
    expect(result).toEqual({ total: 2, registered: 1, failed: 1 });
    expect(registerComponent).toHaveBeenCalledTimes(2);
  });

  it('is a no-op once synced (without force)', async () => {
    registerComponent.mockResolvedValue({});
    await syncCoreCatalog(true);
    const again = await syncCoreCatalog();
    expect(again).toEqual({ total: 0, registered: 0, failed: 0 });
  });
});
