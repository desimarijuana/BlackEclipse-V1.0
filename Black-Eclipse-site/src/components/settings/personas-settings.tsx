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
  UsersThree,
  X,
} from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Field, Panel, SubSection } from '@/components/screens/settings-ui';
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
  'w-full rounded-lg border border-white/10 bg-background/60 px-2.5 py-1.5 text-[12px] text-foreground outline-none focus:border-primary/50';

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
        'rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide',
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
    <div className="space-y-5">
      <SubSection
        icon={UsersThree}
        title="Personas"
        description="A persona changes how Eclipse talks — tone, structure and emphasis. It never changes what Eclipse can do: tools, permissions, data sources and the safety/financial rules stay fixed. One persona is active at a time; editing stages a draft until you activate it."
      >
        {error && (
          <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-2 py-1.5 text-[11px] text-rose-200">
            {error}
          </p>
        )}
        {notice && (
          <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2 py-1.5 text-[11px] text-emerald-200">
            {notice}
          </p>
        )}

        <div className="grid gap-3 lg:grid-cols-[260px_minmax(0,1fr)]">
          <Panel className="p-2">
            <div className="mb-2 flex items-center justify-between px-1">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Your personas
              </span>
              <Button type="button" size="sm" variant="ghost" onClick={() => void create()} disabled={busy} className="gap-1">
                <Plus size={12} /> New
              </Button>
            </div>
            <div className="max-h-[420px] space-y-1 overflow-y-auto">
              <button
                type="button"
                onClick={selectDefault}
                className={cn(
                  'flex w-full items-center justify-between gap-2 rounded-lg border px-2 py-1.5 text-left transition-colors',
                  selectedId === null
                    ? 'border-primary/40 bg-primary/10'
                    : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.05]',
                )}
              >
                <span className="min-w-0">
                  <span className="block truncate text-[12px] font-medium text-foreground">Eclipse default</span>
                  <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                    Built-in prompt · no overlay
                  </span>
                </span>
                {!activePersona && (
                  <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-primary">
                    Active
                  </span>
                )}
              </button>

              {loading && <p className="px-2 py-3 text-[11px] text-muted-foreground">Loading…</p>}
              {!loading && personas.length === 0 && (
                <p className="px-2 py-3 text-[11px] text-muted-foreground">
                  No personas yet. Create one to shape tone and format.
                </p>
              )}
              {personas.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => void open(item.id)}
                  className={cn(
                    'w-full rounded-lg border px-2 py-1.5 text-left transition-colors',
                    selectedId === item.id
                      ? 'border-primary/40 bg-primary/10'
                      : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.05]',
                  )}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="truncate text-[12px] font-medium text-foreground">{item.name}</span>
                    <StatusPill persona={item} />
                  </span>
                  <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                    {item.instructionChars} chars
                    {item.activeVersion ? ` · v${item.activeVersion}` : ' · not published'}
                    {item.hasDraft ? ' · draft pending' : ''}
                  </span>
                </button>
              ))}
            </div>
          </Panel>

          <Panel className="space-y-3 p-3">
            {selectedId === null ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Bot size={14} className="text-primary" />
                  <span className="text-[11px] font-semibold text-foreground">Eclipse default</span>
                </div>
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  The built-in Eclipse prompt is always the base. It is never edited from Settings — a persona is
                  appended after it and clearly marked as lower precedence. Reset removes the overlay; the base prompt
                  is unaffected.
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <Button type="button" size="sm" variant="ghost" onClick={() => void loadPreview()} disabled={busy} className="gap-1">
                    <Eye size={12} /> Preview effective prompt
                  </Button>
                  {activePersona && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => void resetDefault()}
                      disabled={busy}
                      className="gap-1 text-rose-300 hover:text-rose-200"
                    >
                      <RotateCcw size={12} /> Reset to default
                    </Button>
                  )}
                </div>
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-semibold text-foreground">{persona?.name || 'Persona'}</span>
                    {persona && <StatusPill persona={persona} />}
                    {dirty && (
                      <span className="text-[10px] text-amber-200">Unsaved changes</span>
                    )}
                    {!dirty && persona?.hasDraft && (
                      <span className="text-[10px] text-amber-200">Draft saved · not applied</span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => void archive()}
                      disabled={busy}
                      className="gap-1 text-rose-300 hover:text-rose-200"
                    >
                      <Trash2 size={12} /> Archive
                    </Button>
                    <Button type="button" size="sm" variant="ghost" onClick={() => void saveDraft()} disabled={busy || tooLong} className="gap-1">
                      <Save size={12} /> Save draft
                    </Button>
                    <Button type="button" size="sm" onClick={() => void activate()} disabled={busy || tooLong} className="gap-1">
                      <RotateCcw size={12} /> Activate
                    </Button>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
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
                    rows={9}
                    className={cn(inputClass, 'resize-y font-mono text-[11px]')}
                    placeholder="Be terse. Lead with the number, then the evidence. Use tables for multi-asset comparisons."
                  />
                </Field>

                <div className="flex flex-wrap items-center justify-between gap-2 text-[10px]">
                  <span className={cn('tabular-nums', tooLong ? 'text-rose-300' : charCount > WARN_CHARS ? 'text-amber-200' : 'text-muted-foreground')}>
                    {charCount} / {MAX_CHARS} characters
                  </span>
                  <div className="flex items-center gap-1.5">
                    {persona?.hasDraft && (
                      <Button type="button" size="sm" variant="ghost" onClick={() => void discard()} disabled={busy} className="gap-1">
                        <Undo2 size={12} /> Discard draft
                      </Button>
                    )}
                    <Button type="button" size="sm" variant="ghost" onClick={() => void loadPreview()} disabled={busy} className="gap-1">
                      <Eye size={12} /> Preview
                    </Button>
                  </div>
                </div>

                {tooLong && (
                  <p className="flex items-start gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2 py-1.5 text-[11px] text-rose-200">
                    <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                    Instructions are capped at {MAX_CHARS} characters. Shorten them before saving.
                  </p>
                )}

                <div className="space-y-1.5">
                  <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    <History size={12} /> Versions
                  </span>
                  {versions.length === 0 ? (
                    <p className="text-[11px] text-muted-foreground">No published versions yet. Activate to publish v1.</p>
                  ) : (
                    <div className="max-h-[150px] overflow-y-auto rounded-lg border border-white/10">
                      {versions.map((version) => (
                        <div
                          key={version.version}
                          className="flex items-center justify-between gap-2 border-b border-white/[0.04] px-2.5 py-1.5 last:border-0"
                        >
                          <span className="min-w-0">
                            <span className="font-mono text-[10.5px] text-foreground">v{version.version}</span>
                            <span className="ml-2 text-[10px] text-muted-foreground">
                              {version.instructionChars} chars · {version.createdAt.replace('T', ' ').slice(0, 16)}
                            </span>
                          </span>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() => void restore(version.version)}
                            disabled={busy}
                            className="gap-1 text-[10px]"
                          >
                            <Undo2 size={11} /> Restore
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}

            {preview && (
              <div className="space-y-2 rounded-lg border border-white/10 bg-black/20 p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    <Eye size={12} /> Effective prompt
                  </span>
                  <button
                    type="button"
                    onClick={() => setPreview(null)}
                    className="text-muted-foreground hover:text-foreground"
                    aria-label="Close preview"
                  >
                    <X size={13} />
                  </button>
                </div>
                <p className="text-[10px] text-muted-foreground">
                  {preview.effectiveChars} characters total · {preview.isDefault ? 'built-in prompt only' : `overlay: ${preview.persona?.name}`}
                </p>
                <pre className="max-h-[260px] overflow-auto whitespace-pre-wrap rounded bg-background/60 p-2 font-mono text-[10px] leading-relaxed text-foreground/80">
                  {preview.basePrompt}
                  {preview.personaBlock ? `\n\n${preview.personaBlock}` : ''}
                </pre>
              </div>
            )}
          </Panel>
        </div>
      </SubSection>
    </div>
  );
}
