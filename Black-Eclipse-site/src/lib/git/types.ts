// ── Git wire types (client-safe) ──────────────────────────────────────────────
//
// The shapes shared by the server-side front door (`service.ts`) and the browser
// client (`client.ts`). Kept in their own module so the client bundle never has to
// import a server-only module (`service.ts` pulls in the runtime auth + python
// client). No runtime code here — types only.

export interface GitFileChange {
  path: string;
  index: string;
  worktree: string;
  staged: boolean;
}

export interface GitStatus {
  available: boolean;
  branch: string | null;
  upstream: string | null;
  ahead: number;
  behind: number;
  files: GitFileChange[];
  stagedCount: number;
  unstagedCount: number;
  untrackedCount: number;
  clean: boolean;
  reason?: string;
}

export interface GitCommitInfo {
  hash: string;
  shortHash: string;
  subject: string;
  author: string;
  date: string;
}
