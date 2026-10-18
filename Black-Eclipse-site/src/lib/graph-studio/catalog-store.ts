// ── Workflow catalog (shared by the mode panel and the workspace) ────────────
// The Graph Studio mode's left panel and the workspace screen both need the
// workflow list, so it lives in ONE store. Opening a workflow loads it into the
// editor store; creating one persists it first (a workflow always exists on the
// server before it is drawn).

import { create } from 'zustand';
import {
  createWorkflow, deleteWorkflow, getWorkflow, listWorkflows,
  type WorkflowSummary,
} from './persistence-client';
import { buildTemplate } from './templates';
import { useGraphEditor } from './editor-store';

export interface WorkflowCatalogState {
  summaries: WorkflowSummary[];
  loading: boolean;
  busy: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  open: (id: string) => Promise<void>;
  createFromTemplate: (templateId: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  clearError: () => void;
}

export const useWorkflowCatalog = create<WorkflowCatalogState>((set, get) => ({
  summaries: [],
  loading: false,
  busy: false,
  error: null,

  refresh: async () => {
    set({ loading: true });
    try {
      set({ summaries: await listWorkflows(), error: null });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Failed to load workflows' });
    } finally {
      set({ loading: false });
    }
  },

  open: async (id) => {
    set({ busy: true });
    try {
      const record = await getWorkflow(id);
      useGraphEditor.getState().load(record.ir, {
        workflowId: id,
        baseVersion: record.version,
        contentHash: record.contentHash,
      });
      set({ error: null });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Failed to open workflow' });
    } finally {
      set({ busy: false });
    }
  },

  createFromTemplate: async (templateId) => {
    set({ busy: true });
    try {
      const draft = buildTemplate(templateId);
      if (!draft) throw new Error('Unknown template');
      const record = await createWorkflow({ name: draft.name, description: draft.description, ir: draft });
      useGraphEditor.getState().load(record.ir, {
        workflowId: record.id,
        baseVersion: record.version,
        contentHash: record.contentHash,
      });
      set({ error: null });
      await get().refresh();
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Failed to create workflow' });
    } finally {
      set({ busy: false });
    }
  },

  remove: async (id) => {
    set({ busy: true });
    try {
      await deleteWorkflow(id);
      if (useGraphEditor.getState().workflowId === id) useGraphEditor.getState().reset();
      set({ error: null });
      await get().refresh();
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Failed to delete workflow' });
    } finally {
      set({ busy: false });
    }
  },

  clearError: () => set({ error: null }),
}));
