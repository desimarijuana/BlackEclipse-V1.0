// May this process rewrite `.next` right now?
//
// `next build` deletes `BUILD_ID`, rewrites the whole output directory and
// saturates the CPU for several minutes. The desktop window itself is protected
// (it serves an immutable pinned copy, never the live `.next`), but a build that
// starts while the app is running still:
//
//   * starves the Python runtime's cold start, which then misses its budget
//     (measured: the harness needs 33–67 s idle, and took >5 min under a
//     concurrent build), and
//   * leaves `.next` without a `BUILD_ID` until it finishes, so `desktop:doctor`
//     and any promotion see "no available build".
//
// That is the "I built it and the app broke" loop. A plain `npm run build` is
// therefore refused while a channel is live; the MANAGED paths (`desktop:refresh`
// → `desktop-build.js`, and `black update`) set
// `BE_ALLOW_BUILD_WHILE_RUNNING=1` because they own the pin and the restart.
//
// This module is pure (no I/O) so the policy is testable on its own; the caller
// supplies the live-channel probe.

const TRUTHY = new Set(["1", "true", "yes", "on"]);

/** Read the explicit escape hatch. Anything unexpected means "not allowed". */
function allowBuildWhileRunning(raw) {
  return TRUTHY.has(String(raw || "").trim().toLowerCase());
}

/**
 * `true` when the build must be refused.
 *
 * @param {{ live?: Array<{label?: string, appPort?: number, pid?: number}>, allow?: boolean }} input
 */
function shouldRefuseBuild({ live = [], allow = false } = {}) {
  return !allow && Array.isArray(live) && live.length > 0;
}

/** "Stable on http://127.0.0.1:3100 (server pid 1234)". */
function describeLive(live = []) {
  return live
    .map((channel) => {
      const parts = [];
      if (channel.appPort) parts.push(`on http://127.0.0.1:${channel.appPort}`);
      if (channel.pid) parts.push(`(server pid ${channel.pid})`);
      else if (Array.isArray(channel.windowPids) && channel.windowPids.length) {
        parts.push(`(window pid ${channel.windowPids.join(", ")})`);
      }
      return `${channel.label || channel.id || "a channel"}${parts.length ? ` ${parts.join(" ")}` : ""}`;
    })
    .join(" and ");
}

/** The one message a refused build prints. */
function refusalMessage(live = []) {
  const running = describeLive(live);
  return [
    "",
    `[build] refusing to rebuild while the desktop app is running${running ? `: ${running}` : ""}.`,
    "",
    "  `next build` deletes and rewrites .next and saturates the CPU. While the app",
    "  is up that starves the Python runtime's cold start and leaves .next without a",
    "  BUILD_ID until the build finishes.",
    "",
    "Do one of:",
    "  npm run desktop:refresh   build if needed, pin it, and reopen the window  (recommended)",
    "  black stop                stop the app, then run the build",
    "  npm run desktop:dev       work in the Dev channel (3101, separate build)",
    "",
    "  Automated flows that build BEFORE refreshing (black update) set",
    "  BE_ALLOW_BUILD_WHILE_RUNNING=1 themselves.",
    "",
  ].join("\n");
}

module.exports = {
  allowBuildWhileRunning,
  shouldRefuseBuild,
  describeLive,
  refusalMessage,
};
