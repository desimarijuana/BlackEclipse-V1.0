// ── English dictionary — chat notebook (Phase 21) ───────────────────────────
// The language for the editable cells beside a conversation. "Worked out by
// Eclipse" is reused from the analysis slice; these keys add the notebook
// actions, states and the chart-to-cell bridge.

export const notebook = {
  'notebook.title': 'Notebook',
  'notebook.subtitle': 'Run and edit cells for this conversation.',
  'notebook.addCell': 'Add cell',
  'notebook.run': 'Run',
  'notebook.running': 'Running…',
  'notebook.restart': 'Restart',
  'notebook.restarted': 'Notebook restarted. Earlier variables were cleared.',
  'notebook.delete': 'Delete cell',
  'notebook.close': 'Close notebook',
  'notebook.empty': 'No cells yet. Add one, or open a chart and choose Edit code.',
  'notebook.fromChart': 'From a chart',
  'notebook.chartLink': 'Open the original chart',
  'notebook.output': 'Output',
  'notebook.noOutput': 'No output',
  'notebook.computed': 'Worked out by Eclipse',
  'notebook.editCode': 'Edit code',
  'notebook.startingScript': 'Starting script — edit and run it. The original chart stays unchanged.',
  'notebook.unsupported': 'The starting script cannot reproduce: {what}.',
  'notebook.failed': 'The cell could not run.',
  'notebook.figure': 'Figure',
  'notebook.saveFailed': 'Could not save the notebook.',
  'notebook.runFailed': 'The cell could not run.',
  'notebook.restartFailed': 'The notebook could not be restarted.',
  'notebook.sourceLabel': 'Python',
  'notebook.cellLabel': 'Cell {n}',
  'notebook.status.idle': 'Ready',
  'notebook.status.running': 'Running',
  'notebook.status.ok': 'Done',
  'notebook.status.failed': 'Failed',
  'notebook.status.refused': 'Not run',
  'notebook.status.timed_out': 'Timed out',
} as const;
