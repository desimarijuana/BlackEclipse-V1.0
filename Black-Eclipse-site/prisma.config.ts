import path from "node:path";
import { defineConfig } from "prisma/config";

// `BE_DATA_DIR` relocates the personal database onto an encrypted volume. The
// runtime (`src/lib/db.ts`) and the Python stores read the same variable, so the
// CLI (`prisma db push`, `prisma generate`) and the app always agree on one file.
// Forward slashes keep the `file:` URL valid on Windows.
const dataDir = process.env.BE_DATA_DIR
  ? path.resolve(process.env.BE_DATA_DIR)
  : process.cwd();
const databaseUrl = `file:${path.join(dataDir, "jdds.db").replace(/\\/g, "/")}`;

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: {
    path: "prisma/migrations",
  },
  datasource: {
    url: databaseUrl,
  },
});
