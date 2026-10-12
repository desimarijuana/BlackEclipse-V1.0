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
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
});
