#!/usr/bin/env node
// Gate for every retired browser/website command.
//
// The product is desktop-only. The web code stays in the tree for a future
// browser release, but a website server must never start by habit: it shares
// the build tree, competes for CPU and was the source of the "I built it and
// the app broke" loop.
//
// Exit 0 when the web lane is explicitly allowed, 1 otherwise (so an npm `&&`
// chain stops before starting a server).

const { refuseWebLane } = require("./lib/channels");

const command = process.argv.slice(2).join(" ") || "web lane";
process.exit(refuseWebLane(command) ? 1 : 0);
