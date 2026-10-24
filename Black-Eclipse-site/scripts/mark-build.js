#!/usr/bin/env node
// Record the current source as built. Runs as `postbuild` so a plain
// `npm run build` also refreshes the hash `black` uses to skip rebuilds.

const { markBuilt } = require("./lib/server");

markBuilt();
