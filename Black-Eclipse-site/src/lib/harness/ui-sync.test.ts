import { beforeEach, describe, expect, it, vi } from 'vitest';

const registerComponents = vi.hoisted(() =>
  vi.fn(async () => ({ total: 2, registered: 2, failed: [] as { componentId: string; error: string }[] })),
);
const registerSurfaces = vi.hoisted(() =>
  vi.fn(async (_surfaces: unknown[]) => ({ total: 1, registered: 1 })),
);

vi.mock('@/lib/harness/ui-client', () => ({ registerComponents, registerSurfaces }));
vi.mock('@/lib/ui-engineering/registry-catalog', () => ({
  dashboardComponentSpecs: () => [{ id: 'a' }, { id: 'b' }],
}));
vi.mock('@/lib/app-surfaces', () => ({
  appSurfaces: () => [
    { id: 'memory', label: 'Eclipse Memory', deepLink: '/?tab=memory', tabs: [{ id: 'memory.reviews', label: 'Learning Reviews', deepLink: '/?tab=memory&sub=memory.reviews' }] },
  ],
}));

import { syncAppSurfaces, syncCoreCatalog } from './ui-sync';

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

describe('syncAppSurfaces', () => {
  beforeEach(() => registerSurfaces.mockReset());

  it('ships the derived screen inventory in one request', async () => {
    registerSurfaces.mockResolvedValueOnce({ total: 1, registered: 1 });
    const result = await syncAppSurfaces(true);
    expect(result).toEqual({ total: 1, registered: 1, failed: 0 });
    expect(registerSurfaces).toHaveBeenCalledTimes(1);
    expect(registerSurfaces.mock.calls[0][0]).toEqual([
      expect.objectContaining({ id: 'memory', deepLink: '/?tab=memory' }),
    ]);
  });

  it('reports every surface failed when the runtime is down', async () => {
    registerSurfaces.mockRejectedValueOnce(new Error('runtime down'));
    const result = await syncAppSurfaces(true);
    expect(result).toEqual({ total: 1, registered: 0, failed: 1 });
  });

  it('is a no-op once synced (without force)', async () => {
    registerSurfaces.mockResolvedValue({ total: 1, registered: 1 });
    await syncAppSurfaces(true);
    const again = await syncAppSurfaces();
    expect(again).toEqual({ total: 0, registered: 0, failed: 0 });
    expect(registerSurfaces).toHaveBeenCalledTimes(1);
  });
});
