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
    // On GitHub's runner more than one fork dies mid-run ("Worker exited
    // unexpectedly") while every test that ran passed: 527 files each import the
    // agent tool registry, so each fork's resident memory grows with the files it
    // hosts. One worker on CI (local runs keep the default fan-out) costs a couple
    // of minutes and stops the process from being killed.
    maxWorkers: process.env.CI ? 1 : undefined,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
});
