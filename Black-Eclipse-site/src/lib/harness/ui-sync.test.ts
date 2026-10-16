import { beforeEach, describe, expect, it, vi } from 'vitest';

const registerComponents = vi.hoisted(() =>
  vi.fn(async () => ({ total: 2, registered: 2, failed: [] as { componentId: string; error: string }[] })),
);

vi.mock('@/lib/harness/ui-client', () => ({ registerComponents }));
vi.mock('@/lib/ui-engineering/registry-catalog', () => ({
  dashboardComponentSpecs: () => [{ id: 'a' }, { id: 'b' }],
}));

import { syncCoreCatalog } from './ui-sync';

describe('syncCoreCatalog', () => {
  beforeEach(() => registerComponents.mockReset());

  it('registers the whole catalog in one batched request and counts failures', async () => {
    registerComponents.mockResolvedValueOnce({
      total: 2,
      registered: 1,
      failed: [{ componentId: 'b', error: 'runtime down' }],
    });
    const result = await syncCoreCatalog(true);
    expect(result).toEqual({ total: 2, registered: 1, failed: 1 });
    expect(registerComponents).toHaveBeenCalledTimes(1);
  });

  it('reports every spec failed when the runtime rejects the batch', async () => {
    registerComponents.mockRejectedValueOnce(new Error('runtime down'));
    const result = await syncCoreCatalog(true);
    expect(result).toEqual({ total: 2, registered: 0, failed: 2 });
  });

  it('is a no-op once synced (without force)', async () => {
    registerComponents.mockResolvedValue({ total: 2, registered: 2, failed: [] });
    await syncCoreCatalog(true);
    const again = await syncCoreCatalog();
    expect(again).toEqual({ total: 0, registered: 0, failed: 0 });
    expect(registerComponents).toHaveBeenCalledTimes(1);
  });
});
