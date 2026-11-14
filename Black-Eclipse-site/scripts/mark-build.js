#!/usr/bin/env node
// `postbuild` — intentionally a NO-OP.
//
// The source hash that `needsBuild()` compares against must describe the tree
// that `next build` actually COMPILED. It is written by `build()` in
// `scripts/lib/server.js` from a hash taken at build START. Writing it here
// (after the build finishes) would record edits made *during* the build that
// were never compiled — which is exactly how a release shipped a chat bundle
// without the change it claimed to contain.
//
// Kept as a script because `package.json` still calls it; deleting the hook
// would silently change behavior for anyone reading the scripts.

console.log("[postbuild] source hash is recorded at build start; nothing to mark here");
