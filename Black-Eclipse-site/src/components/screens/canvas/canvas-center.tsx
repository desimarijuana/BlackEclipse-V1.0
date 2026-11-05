'use client';

// ─── Canvas center region ─────────────────────────────────────────────────────
// Title with inline rename, kind badge, code-language selector, the save-status
// chip and the toolbar (undo/redo, versions, export, full-width). Hosts the
// editor selected by artifact kind.

import { useEffect, useRef, useState, type MutableRefObject } from 'react';
import {
  AlertTriangle, Check, ChevronDown, Download, FileOutput, History, Loader2,
  Maximize2, Minimize2, Redo2, Save, Trash2, Undo2, Upload,
} from '@/lib/icons';
import type { CanvasSnapshot } from '@/lib/harness/canvas-client';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { CanvasEditor } from './canvas-editors';
import {
  CODE_LANGUAGES, humanTime, kindLabel, monacoLanguage,
  type CanvasEditorHandle, type CanvasSaveState, type CanvasSelection,
} from './canvas-utils';

export interface CanvasCenterProps {
  snapshot: CanvasSnapshot;
  content: string;
  dirty: boolean;
  saveState: CanvasSaveState;
  saveError: string | null;
  onContentChange: (next: string) => void;
  onSelectionChange: (selection: CanvasSelection | null) => void;
  editorHandleRef: MutableRefObject<CanvasEditorHandle | null>;
  onRename: (name: string) => void;
  onLanguageChange: (language: string) => void;
  onRestore: (version: number) => void;
  onExport: (action: 'download' | 'copy' | 'print') => void;
  onSaveNow: () => void;
  onDelete: () => void;
  fullWidth: boolean;
  onToggleFullWidth: () => void;
  editable: boolean;
}

function SaveChip({ state, dirty, error }: { state: CanvasSaveState; dirty: boolean; error: string | null }) {
  let label = 'Saved';
  let tone = 'text-emerald-400';
  let icon = <Check className="h-3.5 w-3.5" />;
  if (state === 'saving') { label = 'Saving…'; tone = 'text-muted-foreground'; icon = <Loader2 className="h-3.5 w-3.5 animate-spin" />; }
  else if (state === 'error') { label = 'Save failed'; tone = 'text-rose-400'; icon = <AlertTriangle className="h-3.5 w-3.5" />; }
  else if (state === 'conflict') { label = 'Conflict'; tone = 'text-amber-400'; icon = <AlertTriangle className="h-3.5 w-3.5" />; }
  else if (dirty) { label = 'Unsaved changes'; tone = 'text-amber-400'; icon = <AlertTriangle className="h-3.5 w-3.5" />; }
  else if (state === 'idle') { label = 'Up to date'; tone = 'text-muted-foreground'; }
  return (
    <span className={cn('flex items-center gap-1.5 text-[11px]', tone)} title={error ?? label}>
      {icon}
      {label}
    </span>
  );
}

const LANGUAGES = Array.from(new Set(CODE_LANGUAGES));

export function CanvasCenter(props: CanvasCenterProps) {
  const {
    snapshot, content, dirty, saveState, saveError, onContentChange, onSelectionChange,
    editorHandleRef, onRename, onLanguageChange, onRestore, onExport, onSaveNow, onDelete,
    fullWidth, onToggleFullWidth, editable,
  } = props;

  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState(snapshot.name);
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setTitleDraft(snapshot.name); }, [snapshot.name]);
  useEffect(() => { if (editingTitle) titleRef.current?.select(); }, [editingTitle]);

  const commitTitle = () => {
    const next = titleDraft.trim();
    setEditingTitle(false);
    if (next && next !== snapshot.name) onRename(next);
    else setTitleDraft(snapshot.name);
  };

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 rounded-2xl glass-card p-4" aria-label="Canvas editor">
      <header className="flex flex-wrap items-center gap-2">
        {editingTitle ? (
          <input
            ref={titleRef}
            value={titleDraft}
            aria-label="Artifact name"
            onChange={(e) => setTitleDraft(e.target.value)}
            onBlur={commitTitle}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitTitle();
              if (e.key === 'Escape') { setTitleDraft(snapshot.name); setEditingTitle(false); }
            }}
            className="glass-card-subtle rounded-lg px-2 py-1 text-lg font-semibold text-foreground outline-none"
          />
        ) : (
          <button
            type="button"
            onClick={() => editable && setEditingTitle(true)}
            disabled={!editable}
            title={editable ? 'Rename' : snapshot.name}
            className="max-w-full truncate rounded-lg px-1 text-left text-lg font-semibold text-foreground hover:bg-white/5 disabled:cursor-default"
          >
            {snapshot.name}
          </button>
        )}
        <span className="rounded-full glass-card-subtle px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground/80">
          {kindLabel(snapshot.kind)}
        </span>
        {snapshot.kind === 'code' ? (
          <select
            aria-label="Language"
            value={monacoLanguage(snapshot.language)}
            onChange={(e) => onLanguageChange(e.target.value)}
            className="rounded-lg glass-card-subtle bg-transparent px-2 py-1 text-xs text-foreground outline-none"
          >
            {LANGUAGES.map((lang) => <option key={lang} value={lang}>{lang}</option>)}
          </select>
        ) : null}
        <span className="ml-auto flex items-center gap-2">
          <SaveChip state={saveState} dirty={dirty} error={saveError} />
          <Button variant="ghost" size="icon-sm" aria-label="Save now" onClick={onSaveNow} disabled={!editable}>
            <Save className="h-4 w-4" />
          </Button>
        </span>
      </header>

      <div className="flex flex-wrap items-center gap-1">
        <Button variant="ghost" size="icon-sm" aria-label="Undo" onClick={() => editorHandleRef.current?.undo?.()}>
          <Undo2 className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label="Redo" onClick={() => editorHandleRef.current?.redo?.()}>
          <Redo2 className="h-4 w-4" />
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" size="sm" />}>
            <History className="h-4 w-4" />
            Versions
            <ChevronDown className="h-3 w-3" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-[280px]">
            <DropdownMenuGroup>
            <DropdownMenuLabel>Version history</DropdownMenuLabel>
            {snapshot.versions.length === 0 ? (
              <div className="px-1.5 py-1 text-xs text-muted-foreground/60">No history yet.</div>
            ) : (
              snapshot.versions.map((v) => (
                <DropdownMenuItem
                  key={v.versionNumber}
                  onClick={() => onRestore(v.versionNumber)}
                  disabled={v.versionNumber === snapshot.version}
                >
                  <span className="flex-1">
                    <span className="block text-xs text-foreground">v{v.versionNumber}{v.versionNumber === snapshot.version ? ' · current' : ''}</span>
                    <span className="block truncate text-[10px] text-muted-foreground/60">
                      {v.changeNote ?? 'No note'} · {humanTime(v.createdAt)}
                    </span>
                  </span>
                </DropdownMenuItem>
              ))
            )}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" size="sm" />}>
            <Download className="h-4 w-4" />
            Export
            <ChevronDown className="h-3 w-3" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-[200px]">
            <DropdownMenuItem onClick={() => onExport('download')}>
              <Download className="h-3.5 w-3.5" /> Download file
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onExport('copy')}>
              <Upload className="h-3.5 w-3.5" /> Copy to clipboard
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => onExport('print')}>
              <FileOutput className="h-3.5 w-3.5" /> Print / PDF
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Archive artifact"
          onClick={onDelete}
          disabled={!editable}
          className="text-rose-300 hover:text-rose-200"
        >
          <Trash2 className="h-4 w-4" />
        </Button>

        <Button
          variant="ghost"
          size="icon-sm"
          className="ml-auto"
          aria-label={fullWidth ? 'Show AI panel' : 'Full-width editor'}
          aria-pressed={fullWidth}
          onClick={onToggleFullWidth}
        >
          {fullWidth ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </Button>
      </div>

      <CanvasEditor
        kind={snapshot.kind}
        content={content}
        language={snapshot.language}
        editable={editable}
        docKey={`${snapshot.artifactId}:${snapshot.version}`}
        onChange={onContentChange}
        onSelectionChange={onSelectionChange}
        handleRef={editorHandleRef}
      />
    </section>
  );
}
