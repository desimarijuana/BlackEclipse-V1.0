// Minimal ambient declaration for `better-sqlite3`, which ships no bundled types
// and is not covered by `@types/better-sqlite3` in this repo. We declare only the
// surface the auth store uses, so `tsc --noEmit` is satisfied without adding a
// dependency. The runtime uses the real module.
//
// This is deliberately narrow: a broader declaration would be a lie about what is
// verified. If the auth store needs more of the driver, extend this.

declare module "better-sqlite3" {
  interface Statement {
    run(...params: unknown[]): { changes: number; lastInsertRowid: number | bigint };
    get(...params: unknown[]): unknown;
    all(...params: unknown[]): unknown[];
  }
  interface Database {
    prepare(sql: string): Statement;
    exec(sql: string): this;
    pragma(source: string): unknown;
    close(): void;
  }
  interface DatabaseConstructor {
    new (filename?: string): Database;
    (filename?: string): Database;
  }
  const Database: DatabaseConstructor;
  export default Database;
}
