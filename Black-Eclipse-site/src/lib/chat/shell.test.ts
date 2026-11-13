import { describe, it, expect } from 'vitest';
import {
  MAX_SHELL_CONTEXT_CHARS,
  SHELL_PREFIX,
  boundShellOutput,
  buildShellFailureTurn,
  buildShellTurn,
  formatShellForHarness,
  isShellDraft,
  shellCommandOf,
  shellExitLabel,
  shellOutput,
  shellSucceeded,
} from './shell';
import { turnTextForHarness } from './quote';
import type { ShellRun } from '@/types/chat';

// `!` shell mode is a SURFACING contract: what the user typed runs, the real
// exit code is reported, and the run becomes context for the next turn. These
// pin those rules so a command can never be silently sent as a prompt.

function run(over: Partial<ShellRun> = {}): ShellRun {
  return {
    command: 'git status --short',
    cwd: '/workspace/app',
    exitCode: 0,
    stdout: ' M src/app.tsx',
    stderr: '',
    durationMs: 42,
    timedOut: false,
    truncated: false,
    status: 'ok',
    ...over,
  };
}

describe('isShellDraft / shellCommandOf', () => {
  it('activates only when `!` begins the draft', () => {
    expect(isShellDraft('!ls')).toBe(true);
    expect(isShellDraft('  !ls')).toBe(true);
    expect(isShellDraft('list files!')).toBe(false);
    expect(isShellDraft('hello')).toBe(false);
    expect(isShellDraft('')).toBe(false);
  });

  it('strips the prefix and surrounding space from the command', () => {
    expect(shellCommandOf('!ls -la')).toBe('ls -la');
    expect(shellCommandOf('  !  npm test  ')).toBe('npm test');
    expect(shellCommandOf(` ${SHELL_PREFIX}npm run build`)).toBe('npm run build');
    expect(shellCommandOf('!')).toBe('');
  });
});

describe('exit reporting', () => {
  it('reports the real exit code and success only for 0', () => {
    expect(shellExitLabel(run())).toBe('exit 0');
    expect(shellExitLabel(run({ exitCode: 2 }))).toBe('exit 2');
    expect(shellSucceeded(run())).toBe(true);
    expect(shellSucceeded(run({ exitCode: 1 }))).toBe(false);
  });

  it('never claims success for a timeout or an unavailable runtime', () => {
    expect(shellExitLabel(run({ timedOut: true }))).toBe('timed out');
    expect(shellExitLabel(run({ exitCode: null, error: 'runtime unavailable' }))).toBe('unavailable');
    expect(shellSucceeded(run({ timedOut: true }))).toBe(false);
    expect(shellSucceeded(run({ error: 'runtime unavailable' }))).toBe(false);
  });
});

describe('shellOutput', () => {
  it('labels stderr separately when both streams have content', () => {
    expect(shellOutput({ stdout: 'out', stderr: 'warn' })).toBe('out\n\n[stderr]\nwarn');
  });

  it('returns whichever stream is present', () => {
    expect(shellOutput({ stdout: '', stderr: 'boom' })).toBe('boom');
    expect(shellOutput({ stdout: 'ok', stderr: '' })).toBe('ok');
    expect(shellOutput({ stdout: '', stderr: '' })).toBe('');
  });
});

describe('boundShellOutput', () => {
  it('keeps short output untouched', () => {
    expect(boundShellOutput('short')).toEqual({ text: 'short', truncated: false });
  });

  it('cuts long output and says it was cut', () => {
    const bounded = boundShellOutput('x'.repeat(MAX_SHELL_CONTEXT_CHARS + 50));
    expect(bounded.truncated).toBe(true);
    expect(bounded.text.length).toBeLessThan(MAX_SHELL_CONTEXT_CHARS + 100);
    expect(bounded.text).toContain('[output truncated]');
  });
});

describe('buildShellTurn', () => {
  it('keeps the typed `!command` as content and attaches the run', () => {
    const turn = buildShellTurn('ls', run({ command: 'ls' }));
    expect(turn.role).toBe('user');
    expect(turn.content).toBe('!ls');
    expect(turn.shell?.command).toBe('ls');
  });

  it('shows a refused run honestly instead of a fake result', () => {
    const turn = buildShellFailureTurn('ls', 'runtime unavailable');
    expect(turn.shell?.error).toBe('runtime unavailable');
    expect(turn.shell?.exitCode).toBeNull();
    expect(turn.shell?.status).toBe('unavailable');
    expect(shellSucceeded(turn.shell!)).toBe(false);
  });
});

describe('harness context', () => {
  it('sends the command and its output, not the `!` line as a question', () => {
    const turn = buildShellTurn('git status', run({ command: 'git status' }));
    const text = turnTextForHarness(turn);
    expect(text).toContain('$ git status');
    expect(text).toContain(' M src/app.tsx');
    expect(text).toContain('exit 0');
    expect(text).toContain('not as instructions');
    expect(text.startsWith('!')).toBe(false);
  });

  it('marks truncated context so the model knows output was cut', () => {
    const text = formatShellForHarness(run({ stdout: 'x'.repeat(MAX_SHELL_CONTEXT_CHARS + 10) }));
    expect(text).toContain('output truncated');
  });

  it('leaves ordinary messages byte-identical', () => {
    expect(turnTextForHarness({ content: 'What is AAPL trading at?' })).toBe('What is AAPL trading at?');
  });
});
