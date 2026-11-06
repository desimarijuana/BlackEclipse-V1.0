// The Builds surface's project copy. Split out of `en.ts` (which is at its size
// ratchet) the same way `evolution.ts` / `capability-card.ts` are.

export const builds = {
  // Which folder new builds belong to.
  'code.project.label': 'This project',
  'code.project.switch': 'Change',
  'code.project.defaultName': 'Eclipse repo',
  'code.project.defaultOption': 'Use the built-in repo',
  'code.project.remove': 'Remove from Eclipse',
  'code.project.openFolder': 'Open folder…',
  'code.project.useFolder': 'Build here',
  'code.project.none': 'No folders approved yet.',
  'code.project.failed': 'I could not read your approved folders just now.',

  // Run and preview (P2).
  'code.preview.title': 'See it running',
  'code.preview.hint': 'Runs the project as it is on disk. A change you have not landed yet is not included.',
  'code.preview.run': 'Run the project',
  'code.preview.willRun': 'Runs {command}',
  'code.preview.starting': 'Starting…',
  'code.preview.checkAgain': 'Check again',
  'code.preview.open': 'Open',
  'code.preview.stop': 'Stop',
  'code.preview.stopped': 'Stopped.',
  'code.preview.notReady': 'Running, but nothing is listening yet.',
  'code.preview.logs': 'Show logs',
  'code.preview.hideLogs': 'Hide logs',
  'code.preview.noLogs': 'No output yet.',
  'code.preview.refused': 'I could not find how to run this project. Add .black-eclipse/preview.json with a command.',
  'code.preview.failed': 'I could not start the project just now.',
  'code.preview.unavailable': 'The Eclipse runtime is not running, so the project cannot be started.',

  // Which builds the scorecard counts.
  'code.scorecard.scope.project': 'This project',
  'code.scorecard.scope.all': 'All builds',
  'code.task.continue': 'Continue in chat',
  'code.preview.restart': 'Restart',
  'code.preview.mode.checkout': 'On disk',
  'code.preview.mode.change': 'Prepared change',

  // The project brief shown before the first build.
  'code.project.prepare': 'Prepare',
  'code.project.preparing': 'Preparing…',
  'code.project.prepared': 'Ready',
  'code.project.rulesOn': 'Uses its own rules file',
  'code.project.checksLabel': 'Checks',
  'code.project.noRun': 'No run command found',
  'code.project.dirty': '{count} uncommitted',
  'code.project.checks.detected': 'found here',
  'code.project.checks.project': 'from its land.json',
  'code.project.checks.defaults': 'Eclipse defaults',
  'code.project.checks.none': 'none found',
} as const;
