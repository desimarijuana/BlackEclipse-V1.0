// ── Make the open Canvas view editable ──────────────────────────────────────
// A response opened with "Open in Canvas" is a read-only snapshot. Editing
// starts by turning that snapshot into a real canvas artifact (the canonical,
// versioned surface) and opening the artifact-backed editor. Shared by the dock
// header and the chat banner so both paths behave identically.

import { createCanvasArtifact } from '@/lib/harness/clients/canvas-client';
import { responseToJson } from '@/lib/response/export';
import { useCommandStore, type CanvasSource } from '@/lib/search/store';

/** Save the ephemeral Canvas view as an artifact and open it for editing. */
export async function makeCanvasEditable(): Promise<string> {
  const state = useCommandStore.getState();
  const content = state.canvasView;
  if (!content) throw new Error('Nothing is open in Canvas.');
  if (content.artifactId) {
    state.openCanvas(content.artifactId, state.canvasSource ?? { title: content.title });
    return content.artifactId;
  }

  const kind = content.kind === 'code' ? 'code' : content.kind === 'report' ? 'visual' : 'document';
  const text = content.kind === 'code'
    ? content.code?.text ?? ''
    : content.kind === 'report' && content.response
      ? responseToJson(content.response)
      : content.markdown ?? '';
  const snapshot = await createCanvasArtifact({
    name: content.title,
    kind,
    language: content.kind === 'code' ? content.code?.language : undefined,
    content: text,
  });
  // Keep the source so the chat banner stays tied to the message it came from.
  const source: CanvasSource = state.canvasSource ?? { title: content.title };
  state.openCanvas(snapshot.artifactId, source);
  return snapshot.artifactId;
}
