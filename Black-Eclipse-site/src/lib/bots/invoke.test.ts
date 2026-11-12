import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AutomationView } from '@/lib/harness/clients/automation-client';
import { getGraphRun, startWorkflowRun } from '@/lib/graph-studio/execution-client';
import { runBotTurn, runWorkflowTurn } from './invoke';

const { mockChat } = vi.hoisted(() => ({ mockChat: vi.fn() }));

vi.mock('@/lib/graph-studio/execution-client', () => ({
  startWorkflowRun: vi.fn(),
  getGraphRun: vi.fn(),
  isTerminal: (status: string) => ['succeeded', 'failed', 'cancelled'].includes(status),
}));

vi.mock('@/lib/agent/registry', () => ({
  getAgentProvider: () => ({ chat: mockChat }),
}));

const mockStart = vi.mocked(startWorkflowRun);
const mockGet = vi.mocked(getGraphRun);

function workflowBot(workflowId: string | null = 'wf_1'): AutomationView {
  return {
    id: 'bot_1',
    name: 'Workflow bot',
    description: null,
    action: {
      type: 'execute_workflow',
      objective: 'Run it',
      agentId: null,
      workflowId,
      workflowInput: {},
      toolName: null,
      toolArgs: {},
      taskTitle: null,
      skillId: null,
      skillVersion: null,
      workspaceRoot: null,
      autonomy: null,
      notificationTemplate: null,
      credentialRef: null,
      config: {},
    },
  } as AutomationView;
}

function agentBot(config: Record<string, unknown> = {}, agentId = 'agt_brain'): AutomationView {
  const bot = workflowBot();
  return {
    ...bot,
    action: {
      ...bot.action,
      type: 'run_agent',
      agentId,
      workflowId: null,
      config,
    },
  } as AutomationView;
}

describe('agent bot turn — brain and model parity', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockChat.mockResolvedValue('ok');
  });

  it('forwards the bot brain and pinned provider/model to the chat run', async () => {
    await runBotTurn({
      bot: agentBot({ modelSettings: { provider: 'openai', model: 'gpt-pinned' } }),
      text: 'hi',
      prior: [],
    });
    expect(mockChat).toHaveBeenCalledWith(
      expect.any(Array),
      undefined,
      expect.objectContaining({
        agentId: 'agt_brain',
        chatId: 'bot-bot_1',
        model: 'gpt-pinned',
        modelProvider: 'openai',
      }),
    );
  });

  it('lets a caller model win without carrying the bot provider pin', async () => {
    await runBotTurn({
      bot: agentBot({ modelSettings: { provider: 'openai', model: 'gpt-pinned' } }),
      text: 'hi',
      prior: [],
      model: 'caller-model',
    });
    const options = mockChat.mock.calls[0][2] as { model?: string; modelProvider?: string };
    expect(options.model).toBe('caller-model');
    expect(options.modelProvider).toBeUndefined();
  });

  it('defaults an unpinned bot to the standard Eclipse brain', async () => {
    await runBotTurn({ bot: agentBot({}, 'eclipse-agent'), text: 'hi', prior: [] });
    const options = mockChat.mock.calls[0][2] as { agentId?: string; model?: string };
    expect(options.agentId).toBe('eclipse-agent');
    expect(options.model).toBeUndefined();
  });
});

describe('workflow bot turn', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('passes the message as run input and returns the terminal output', async () => {
    mockStart.mockResolvedValue({ id: 'run_1', status: 'running' } as never);
    mockGet
      .mockResolvedValueOnce({ id: 'run_1', status: 'running' } as never)
      .mockResolvedValueOnce({
        id: 'run_1',
        status: 'succeeded',
        output: { message: 'hello from the graph' },
      } as never);

    const deltas: string[] = [];
    const reply = await runWorkflowTurn({
      bot: workflowBot(),
      text: 'hi',
      onDelta: (chunk) => deltas.push(chunk),
      pollMs: 0,
    });

    expect(mockStart).toHaveBeenCalledWith('wf_1', undefined, {
      runInput: { message: 'hi', botId: 'bot_1' },
    });
    expect(reply).toBe('hello from the graph');
    expect(deltas).toEqual(['hello from the graph']);
  });

  it('surfaces a failed workflow as an error', async () => {
    mockStart.mockResolvedValue({ id: 'run_1', status: 'running' } as never);
    mockGet.mockResolvedValue({ id: 'run_1', status: 'failed', error: 'boom' } as never);
    await expect(runWorkflowTurn({ bot: workflowBot(), text: 'hi', pollMs: 0 }))
      .rejects.toThrow('boom');
  });

  it('refuses a bot without a workflow', async () => {
    await expect(runWorkflowTurn({ bot: workflowBot(null), text: 'hi', pollMs: 0 }))
      .rejects.toThrow(/no workflow configured/i);
    expect(mockStart).not.toHaveBeenCalled();
  });
});
