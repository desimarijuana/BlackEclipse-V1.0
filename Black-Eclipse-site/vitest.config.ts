import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  // tsconfig.json sets `jsx: "preserve"` for Next, which the default (oxc)
  // transformer honors and therefore leaves JSX untransformed — invalid in the
  // test runtime. Disable oxc so esbuild transforms TSX with the automatic JSX
  // runtime instead. Test-only; the Next build is unaffected.
  oxc: false,
  esbuild: { jsx: 'automatic' },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    // Dynamic imports of the agent/tool modules can take seconds on a loaded
    // Windows machine. The default 5s turned a slow import into a false failure;
    // assertions still run at full strength.
    testTimeout: 15_000,
    // On GitHub's 4-vCPU runner the default one-fork-per-core fan-out was killed
    // mid-run ("Worker exited unexpectedly" x2) while every test that ran passed -
    // 527 files each importing the agent tool registry is too much resident memory.
    // Cap the pool on CI only; local runs keep the default.
    maxWorkers: process.env.CI ? 2 : undefined,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
});
