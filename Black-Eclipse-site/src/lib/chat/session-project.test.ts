import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import {
  SessionError,
  readSessionProject,
  readSessionWorkspaceRootId,
  writeSessionProject,
} from './session-store';

let root: string;

beforeEach(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), 'be-project-'));
  process.env.BLACK_ECLIPSE_SESSION_ROOT = root;
});

afterEach(async () => {
  delete process.env.BLACK_ECLIPSE_SESSION_ROOT;
  await fs.rm(root, { recursive: true, force: true });
});

describe('per-chat project folder', () => {
  it('has no binding until one is written', async () => {
    expect(await readSessionProject('chat_1')).toBeNull();
    expect(await readSessionWorkspaceRootId('chat_1')).toBeUndefined();
  });

  it('persists an approved root id and its display path', async () => {
    const project = await writeSessionProject('chat_1', {
      workspaceRootId: 'root_abc',
      workspacePath: 'C:/projects/demo',
    });
    expect(project.workspaceRootId).toBe('root_abc');
    expect(project.workspacePath).toBe('C:/projects/demo');

    const read = await readSessionProject('chat_1');
    expect(read?.workspaceRootId).toBe('root_abc');
    expect(await readSessionWorkspaceRootId('chat_1')).toBe('root_abc');
  });

  it('clears the binding without touching other chats', async () => {
    await writeSessionProject('chat_1', { workspaceRootId: 'root_a', workspacePath: 'C:/a' });
    await writeSessionProject('chat_2', { workspaceRootId: 'root_b', workspacePath: 'C:/b' });
    await writeSessionProject('chat_1', { workspaceRootId: null, workspacePath: null });
    expect(await readSessionWorkspaceRootId('chat_1')).toBeUndefined();
    expect(await readSessionWorkspaceRootId('chat_2')).toBe('root_b');
  });

  it('rejects a path-traversal chat id', async () => {
    await expect(readSessionProject('../escape')).rejects.toBeInstanceOf(SessionError);
  });
});
