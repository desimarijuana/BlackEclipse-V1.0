'use client';

// ── Settings › Persona ───────────────────────────────────────────────────────
// A persona is a bounded, append-only overlay on the built-in Eclipse prompt —
// never a replacement. The runtime owns sanitization, versions and the
// one-active rule; this panel is a thin draft/active surface plus a preview of
// exactly what the model receives.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Bot,
  Eye,
  History,
  Plus,
  RotateCcw,
  Save,
  Trash2,
  Undo2,
  X,
} from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Field, Panel } from '@/components/screens/settings-ui';
import {
  PersonaApiError,
  activatePersona,
  archivePersona,
  createPersona,
  discardPersonaDraft,
  getPersona,
  getPersonaPreview,
  listPersonaVersions,
  listPersonas,
  resetDefaultPersona,
  restorePersonaVersion,
  updatePersona,
  type Persona,
  type PersonaPreview,
  type PersonaSummary,
  type PersonaVersion,
} from '@/lib/personas/client';

const MAX_CHARS = 2000;
const WARN_CHARS = 1500;

const inputClass =
  'w-full rounded-lg border border-white/10 bg-background/60 px-3 py-2 text-[13px] text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-primary/50';

function statusLabel(persona: PersonaSummary): string {
  if (persona.isActive) return 'Active';
  if (persona.hasDraft) return 'Draft';
  return 'Inactive';
}

function StatusPill({ persona }: { persona: PersonaSummary }) {
  const active = persona.isActive;
  const draft = !active && persona.hasDraft;
  return (
    <span
      className={cn(
        'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
        active
          ? 'bg-primary/15 text-primary'
          : draft
            ? 'bg-amber-500/15 text-amber-200'
            : 'bg-white/5 text-muted-foreground',
      )}
    >
      {statusLabel(persona)}
    </span>
  );
}

/** One selectable persona tile in the picker. */
function PersonaTile({
  selected,
  title,
  subtitle,
  icon,
  status,
  onClick,
}: {
  selected: boolean;
  title: string;
  subtitle: string;
  icon?: React.ReactNode;
  status?: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full items-start gap-2.5 rounded-xl border p-3 text-left transition-colors',
        selected
          ? 'border-primary/40 bg-primary/10'
          : 'border-white/10 bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.05]',
      )}
    >
      {icon && (
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-primary">
          {icon}
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="flex items-start justify-between gap-2">
          <span className="truncate text-xs font-medium text-foreground">{title}</span>
          {status}
        </span>
        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{subtitle}</span>
      </span>
    </button>
  );
}

export function PersonaSettingsPanel() {
  const [personas, setPersonas] = useState<PersonaSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [persona, setPersona] = useState<Persona | null>(null);
  const [versions, setVersions] = useState<PersonaVersion[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [preview, setPreview] = useState<PersonaPreview | null>(null);

  const refresh = useCallback(async () => {
    try {
      setPersonas(await listPersonas());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load personas');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const open = useCallback(async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      const next = await getPersona(id);
      setSelectedId(id);
      setPersona(next);
      setName(next.name);
      setDescription(next.description);
      setInstructions(next.draftInstructions ?? next.instructions);
      setVersions(await listPersonaVersions(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load the persona');
    } finally {
      setBusy(false);
    }
  }, []);

  const selectDefault = () => {
    setSelectedId(null);
    setPersona(null);
    setVersions([]);
    setName('');
    setDescription('');
    setInstructions('');
  };

  const dirty = useMemo(() => {
    if (!persona) return false;
    const baseInstructions = persona.draftInstructions ?? persona.instructions;
    return (
      name !== persona.name ||
      description !== persona.description ||
      instructions !== baseInstructions
    );
  }, [persona, name, description, instructions]);

  const charCount = instructions.length;
  const tooLong = charCount > MAX_CHARS;

  const saveDraft = async () => {
    if (!persona) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await updatePersona(
        persona.id,
        { name, description, instructions },
        persona.revision,
      );
      setPersona(saved);
      setName(saved.name);
      setDescription(saved.description);
      setInstructions(saved.draftInstructions ?? saved.instructions);
      await refresh();
      setNotice('Draft saved. Activate it when you are ready.');
    } catch (err) {
      if (err instanceof PersonaApiError && err.status === 409) {
        await open(persona.id);
        setError(err.message);
        return;
      }
      setError(err instanceof PersonaApiError ? err.message : err instanceof Error ? err.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const activate = async () => {
    if (!persona) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (dirty) {
        await updatePersona(
          persona.id,
          { name, description, instructions },
          persona.revision,
        );
      }
      const saved = await activatePersona(persona.id);
      setPersona(saved);
      setName(saved.name);
      setDescription(saved.description);
      setInstructions(saved.instructions);
      setVersions(await listPersonaVersions(saved.id));
      await refresh();
      setNotice(`${saved.name} is active. New runs use it; earlier runs keep their version.`);
    } catch (err) {
      if (err instanceof PersonaApiError && err.status === 409) {
        await open(persona.id);
        setError(err.message);
        return;
      }
      setError(err instanceof PersonaApiError ? err.message : err instanceof Error ? err.message : 'Activation failed');
    } finally {
      setBusy(false);
    }
  };

  const discard = async () => {
    if (!persona) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const restored = await discardPersonaDraft(persona.id);
      setPersona(restored);
      setName(restored.name);
      setDescription(restored.description);
      setInstructions(restored.instructions);
      await refresh();
      setNotice('Draft discarded — back to the active text.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Discard failed');
    } finally {
      setBusy(false);
    }
  };

  const restore = async (version: number) => {
    if (!persona) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const restored = await restorePersonaVersion(persona.id, version);
      setPersona(restored);
      setInstructions(restored.draftInstructions ?? restored.instructions);
      await refresh();
      setNotice(`v${version} loaded into the draft. Review it, then Activate.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Restore failed');
    } finally {
      setBusy(false);
    }
  };

  const resetDefault = async () => {
    if (!window.confirm('Deactivate the current persona? The built-in Eclipse prompt alone will govern.')) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await resetDefaultPersona();
      selectDefault();
      await refresh();
      setNotice('No persona is active. The built-in prompt alone governs.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed');
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createPersona({ name: 'New persona', description: '', instructions: '' });
      await refresh();
      await open(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create a persona');
    } finally {
      setBusy(false);
    }
  };

  const archive = async () => {
    if (!persona) return;
    if (!window.confirm(`Archive “${persona.name}”? Its version history is kept.`)) return;
    setBusy(true);
    try {
      await archivePersona(persona.id);
      selectDefault();
      await refresh();
      setNotice('Persona archived.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Archive failed');
    } finally {
      setBusy(false);
    }
  };

  const loadPreview = async () => {
    setBusy(true);
    setError(null);
    try {
      setPreview(await getPersonaPreview());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Preview failed');
    } finally {
      setBusy(false);
    }
  };

  const activePersona = personas.find((item) => item.isActive) ?? null;

  return (
    <div className="space-y-4">
      {error && (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[12px] text-rose-200">
          {error}
        </p>
      )}
      {notice && (
        <p className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-[12px] text-emerald-200">
          {notice}
        </p>
      )}

      {/* ── Picker ──────────────────────────────────────────────────────
          A wrapping grid of tiles instead of a 260px rail: the settings
          column is only ~768px wide, so a fixed sidebar squeezed the editor
          into ~480px. The full-width editor below now gets the room. */}
      <Panel className="p-4">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-xs font-semibold tracking-tight text-foreground">Your personas</h3>
            <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
              Pick one to edit. Editing stages a draft; one persona is active at a time.
            </p>
          </div>
          <Button type="button" size="sm" variant="ghost" onClick={() => void create()} disabled={busy} className="gap-1.5">
            <Plus size={13} /> New persona
          </Button>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <PersonaTile
            selected={selectedId === null}
            title="Eclipse default"
            subtitle="Built-in prompt · no overlay"
            icon={<Bot size={15} />}
            status={
              !activePersona ? (
                <span className="shrink-0 rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                  Active
                </span>
              ) : undefined
            }
            onClick={selectDefault}
          />

          {personas.map((item) => (
            <PersonaTile
              key={item.id}
              selected={selectedId === item.id}
              title={item.name}
              subtitle={`${item.instructionChars} chars${
                item.activeVersion ? ` · v${item.activeVersion}` : ' · not published'
              }${item.hasDraft ? ' · draft pending' : ''}`}
              status={<StatusPill persona={item} />}
              onClick={() => void open(item.id)}
            />
          ))}
        </div>

        {loading && <p className="mt-3 px-1 text-[11px] text-muted-foreground">Loading…</p>}
        {!loading && personas.length === 0 && (
          <p className="mt-3 px-1 text-[11px] text-muted-foreground">
            No personas yet. Create one to shape tone and format.
          </p>
        )}
      </Panel>

      {/* ── Editor / detail ─────────────────────────────────────────── */}
      <Panel className="p-4">
        {selectedId === null ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-primary">
                <Bot size={15} />
              </span>
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-foreground">Eclipse default</h3>
                <p className="text-[11px] text-muted-foreground">Built-in prompt only</p>
              </div>
            </div>
            <p className="max-w-xl text-[12px] leading-relaxed text-muted-foreground">
              The built-in Eclipse prompt is always the base. It is never edited from Settings — a persona is
              appended after it and clearly marked as lower precedence. Reset removes the overlay; the base prompt
              is unaffected.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" size="sm" variant="ghost" onClick={() => void loadPreview()} disabled={busy} className="gap-1.5">
                <Eye size={13} /> Preview effective prompt
              </Button>
              {activePersona && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => void resetDefault()}
                  disabled={busy}
                  className="gap-1.5 text-rose-300 hover:text-rose-200"
                >
                  <RotateCcw size={13} /> Reset to default
                </Button>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/[0.06] pb-3">
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="truncate text-sm font-semibold text-foreground">{persona?.name || 'Persona'}</h3>
                  {persona && <StatusPill persona={persona} />}
                </div>
                {dirty ? (
                  <p className="text-[11px] text-amber-200">Unsaved changes</p>
                ) : persona?.hasDraft ? (
                  <p className="text-[11px] text-amber-200">Draft saved · not applied</p>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => void archive()}
                  disabled={busy}
                  className="gap-1.5 text-rose-300 hover:text-rose-200"
                >
                  <Trash2 size={13} /> Archive
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => void saveDraft()} disabled={busy || tooLong} className="gap-1.5">
                  <Save size={13} /> Save draft
                </Button>
                <Button type="button" size="sm" onClick={() => void activate()} disabled={busy || tooLong} className="gap-1.5">
                  <RotateCcw size={13} /> Activate
                </Button>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Name">
                <input value={name} onChange={(event) => setName(event.target.value)} className={inputClass} placeholder="Gold desk analyst" />
              </Field>
              <Field label="Description">
                <input
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  className={inputClass}
                  placeholder="Terse intraday voice"
                />
              </Field>
            </div>

            <Field
              label="Instructions"
              hint="Appended after the authoritative Eclipse prompt. Tone, structure and emphasis only — it cannot add tools, permissions or data sources."
            >
              <textarea
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
                rows={10}
                className={cn(inputClass, 'min-h-[200px] resize-y font-mono text-[12px] leading-relaxed')}
                placeholder="Be terse. Lead with the number, then the evidence. Use tables for multi-asset comparisons."
              />
            </Field>

            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className={cn('text-[11px] tabular-nums', tooLong ? 'text-rose-300' : charCount > WARN_CHARS ? 'text-amber-200' : 'text-muted-foreground')}>
                {charCount} / {MAX_CHARS} characters
              </span>
              <div className="flex items-center gap-1.5">
                {persona?.hasDraft && (
                  <Button type="button" size="sm" variant="ghost" onClick={() => void discard()} disabled={busy} className="gap-1.5">
                    <Undo2 size={13} /> Discard draft
                  </Button>
                )}
                <Button type="button" size="sm" variant="ghost" onClick={() => void loadPreview()} disabled={busy} className="gap-1.5">
                  <Eye size={13} /> Preview
                </Button>
              </div>
            </div>

            {tooLong && (
              <p className="flex items-start gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[12px] text-rose-200">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                Instructions are capped at {MAX_CHARS} characters. Shorten them before saving.
              </p>
            )}

            <div className="space-y-2 border-t border-white/[0.06] pt-4">
              <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                <History size={13} /> Versions
              </span>
              {versions.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">No published versions yet. Activate to publish v1.</p>
              ) : (
                <div className="max-h-[180px] overflow-y-auto rounded-xl border border-white/10">
                  {versions.map((version) => (
                    <div
                      key={version.version}
                      className="flex items-center justify-between gap-3 border-b border-white/[0.04] px-3 py-2 transition-colors last:border-0 hover:bg-white/[0.03]"
                    >
                      <span className="min-w-0">
                        <span className="font-mono text-[12px] text-foreground">v{version.version}</span>
                        <span className="ml-2 text-[11px] text-muted-foreground">
                          {version.instructionChars} chars · {version.createdAt.replace('T', ' ').slice(0, 16)}
                        </span>
                      </span>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => void restore(version.version)}
                        disabled={busy}
                        className="shrink-0 gap-1 text-[11px]"
                      >
                        <Undo2 size={12} /> Restore
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {preview && (
          <div className="mt-4 space-y-2 rounded-xl border border-white/10 bg-black/20 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                <Eye size={13} /> Effective prompt
              </span>
              <button
                type="button"
                onClick={() => setPreview(null)}
                className="text-muted-foreground transition-colors hover:text-foreground"
                aria-label="Close preview"
              >
                <X size={14} />
              </button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              {preview.effectiveChars} characters total · {preview.isDefault ? 'built-in prompt only' : `overlay: ${preview.persona?.name}`}
            </p>
            <pre className="max-h-[300px] overflow-auto whitespace-pre-wrap rounded-lg bg-background/60 p-3 font-mono text-[11px] leading-relaxed text-foreground/80">
              {preview.basePrompt}
              {preview.personaBlock ? `\n\n${preview.personaBlock}` : ''}
            </pre>
          </div>
        )}
      </Panel>
    </div>
  );
}
