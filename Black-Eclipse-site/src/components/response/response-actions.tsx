'use client';

// ── ResponseActions — export + persist a response ─────────────────────────────
// Three real actions on the response header: download JSON, download PDF (with
// embedded chart images), and save to the existing Artifact Center. The artifact
// save reuses `registerArtifact` → POST /api/artifacts — the SAME store the rest
// of the app uses; there is no second artifact system. If the Python runtime is
// unavailable the save reports it honestly (503 → error state).

import { useState } from 'react';
import { Check, Database, FileOutput, FileText, SquarePen } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { ParsedResponse } from '@/lib/response/contract';
import {
  downloadResponseJson,
  downloadResponseMarkdown,
  downloadResponsePdf,
  responseToJson,
  toBase64Utf8,
} from '@/lib/response/export';
import { registerArtifact } from '@/lib/harness/clients/artifacts-browser';
import { contentFromResponse } from '@/lib/canvas/content';
import { toMarkdownProjection } from '@/lib/response/projection';
import { TtsButton } from '@/components/chat/tts-button';
import { useCommandStore } from '@/lib/search/store';
import { useResponseRuntime } from './figure-context';

export interface ResponseActionsProps {
  response: ParsedResponse;
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

const btn =
  'inline-flex items-center gap-1 rounded-full border border-border/50 px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-40';

function responseName(response: ParsedResponse): string {
  return response.title || response.responseId || 'eclipse-response';
}

export function ResponseActions({ response }: ResponseActionsProps) {
  const { stateKey } = useResponseRuntime();
  const [save, setSave] = useState<SaveState>('idle');
  const [savedId, setSavedId] = useState<string | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const saveArtifact = async () => {
    setSave('saving');
    setError(null);
    try {
      const artifact = await registerArtifact({
        name: `${responseName(response)}.eclipse.json`,
        contentBase64: toBase64Utf8(responseToJson(response)),
        description: response.summary ?? 'Structured Eclipse response',
        category: 'report',
        tags: ['eclipse-response', response.responseType ?? 'response'],
      });
      setSavedId(artifact.id);
      setSave('saved');
    } catch (e) {
      setSave('error');
      setError(e instanceof Error ? e.message : 'Save failed');
    }
  };

  const exportPdf = async () => {
    setPdfBusy(true);
    setError(null);
    try {
      await downloadResponsePdf(response, responseName(response));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'PDF export failed');
    } finally {
      setPdfBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-1">
      <button type="button" className={btn} onClick={() => downloadResponseJson(response, responseName(response))} title="Download response as JSON">
        <FileText size={11} /> JSON
      </button>
      <TtsButton
        content={toMarkdownProjection(response)}
        speakKey={response.responseId}
        variant="pill"
        label="Read aloud"
      />
      <button type="button" className={btn} onClick={() => downloadResponseMarkdown(response, responseName(response))} title="Download response as Markdown">
        <FileText size={11} /> MD
      </button>
      <button type="button" className={cn(btn, pdfBusy && 'opacity-60')} onClick={() => void exportPdf()} disabled={pdfBusy} title="Download response as PDF">
        <FileOutput size={11} /> {pdfBusy ? 'PDF…' : 'PDF'}
      </button>
      <button
        type="button"
        className={cn(btn, save === 'error' && 'border-rose-500/40 text-rose-300')}
        onClick={() => void saveArtifact()}
        disabled={save === 'saving'}
        title="Save to Artifact Center"
      >
        {save === 'saved' ? <Check size={11} /> : <Database size={11} />}
        {save === 'saving' ? 'Saving…' : save === 'saved' ? 'Saved' : 'Save'}
      </button>
      <button
        type="button"
        className={btn}
        onClick={() => {
          const content = contentFromResponse(response);
          useCommandStore.getState().openCanvasContent(
            content,
            stateKey ? { messageId: stateKey, title: content.title || 'Canvas' } : undefined,
          );
        }}
        title="Open in Canvas — read this at full width"
      >
        <SquarePen size={11} /> Open in Canvas
      </button>
      {savedId && (
        <button
          type="button"
          className={btn}
          onClick={() => useCommandStore.getState().dispatch({ tab: 'chat', params: { artifactId: savedId } })}
          title="Edit this saved artifact in Canvas"
        >
          <SquarePen size={11} /> Edit
        </button>
      )}
      {error && <span className="text-[10px] text-rose-300/80" title={error}>{error}</span>}
    </div>
  );
}

export default ResponseActions;
