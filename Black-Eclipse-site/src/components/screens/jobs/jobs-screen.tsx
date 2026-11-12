'use client';

// ── The jobs screen (Phase 6) ────────────────────────────────────────────────
// List + editor + history + library. Everything user-facing is a plain finance
// sentence; mechanism lives behind "details". All strings are i18n keys.

import { useCallback, useEffect, useState } from 'react';
import { useT } from '@/lib/i18n/use-t';
import {
  createJob,
  deleteJob,
  listJobRuns,
  listJobs,
  listJobTemplates,
  resetJobBreaker,
  runJobNow,
  setJobEnabled,
  type CreateJobInput,
  type JobDefinitionView,
  type JobRunView,
  type JobTemplateView,
} from '@/lib/harness/clients/jobs-browser';
import { JobList } from './job-list';
import { JobEditor } from './job-editor';
import { JobDetail } from './job-detail';
import { TemplatePicker } from './template-picker';

export function JobsScreen() {
  const t = useT();
  const [jobs, setJobs] = useState<JobDefinitionView[]>([]);
  const [templates, setTemplates] = useState<JobTemplateView[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [runs, setRuns] = useState<JobRunView[]>([]);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextJobs, nextTemplates] = await Promise.all([listJobs(), listJobTemplates()]);
      setJobs(nextJobs);
      setTemplates(nextTemplates);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'could not load jobs');
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const selected = jobs.find((j) => j.id === selectedId) ?? null;

  useEffect(() => {
    if (!selectedId) { setRuns([]); return; }
    void listJobRuns(selectedId).then(setRuns).catch(() => setRuns([]));
  }, [selectedId, jobs]);

  async function handleSave(input: CreateJobInput) {
    const { job } = await createJob(input);
    setEditing(false);
    await refresh();
    setSelectedId(job.id);
  }

  async function handleUseTemplate(templateId: string, params: Record<string, string>) {
    try {
      const { job } = await createJob({ templateId, params });
      await refresh();
      setSelectedId(job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'could not create the job');
    }
  }

  return (
    <div className="space-y-3 p-4">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-[15px] font-medium text-foreground">{t('jobs.title')}</h2>
          <p className="text-[12px] text-muted-foreground">{t('jobs.description')}</p>
        </div>
        <button
          type="button"
          onClick={() => { setEditing(true); setSelectedId(null); }}
          className="glass-button rounded-lg px-3 py-1.5 text-[12px] text-foreground"
        >
          {t('jobs.create')}
        </button>
      </header>

      {error && (
        <div className="glass-card-subtle rounded-xl border border-red-500/30 p-2.5 text-[12px] text-red-300">
          {error}
        </div>
      )}

      {editing && (
        <JobEditor onSave={handleSave} onCancel={() => setEditing(false)} />
      )}

      {!editing && jobs.length === 0 && (
        <TemplatePicker templates={templates} onUse={handleUseTemplate} />
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        <JobList jobs={jobs} selectedId={selectedId} onSelect={setSelectedId} />
        {selected && (
          <JobDetail
            job={selected}
            runs={runs}
            onEnable={() => { void setJobEnabled(selected.id, true).then(refresh); }}
            onDisable={() => { void setJobEnabled(selected.id, false).then(refresh); }}
            onRunNow={() => { void runJobNow(selected.id).then(refresh).catch((e) => setError(String(e))); }}
            onReset={() => { void resetJobBreaker(selected.id).then(refresh); }}
            onDelete={() => { void deleteJob(selected.id).then(() => { setSelectedId(null); return refresh(); }); }}
          />
        )}
      </div>
    </div>
  );
}
