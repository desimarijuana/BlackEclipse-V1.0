import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
      // Generated Prisma client — vendored output, never hand-edited.
      "src/generated/**",
      // One-off Node import/utility scripts (plain JS, not part of the app).
      "scripts/**",
      "check-browser.ts",
      "check-gf.ts",
    ],
  },
];

export default eslintConfig;
