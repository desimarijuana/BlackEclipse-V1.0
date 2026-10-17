'use client';

// ─── Canvas code editor (Monaco) ──────────────────────────────────────────────
// Loaded through `next/dynamic` with `ssr: false`. Maps the artifact language to
// a Monaco language id and reports the current selection as character offsets so
// the AI panel can propose a scoped edit.

import { useRef, type MutableRefObject } from 'react';
import Editor, { type OnChange, type OnMount } from '@monaco-editor/react';
import { monacoLanguage, type CanvasEditorHandle, type CanvasSelection } from './canvas-utils';

export interface CodeEditorProps {
  content: string;
  language?: string | null;
  editable?: boolean;
  onChange: (next: string) => void;
  onSelectionChange?: (selection: CanvasSelection | null) => void;
  handleRef?: MutableRefObject<CanvasEditorHandle | null>;
}

export default function CodeEditor({
  content, language, editable = true, onChange, onSelectionChange, handleRef,
}: CodeEditorProps) {
  const selectionSub = useRef<{ dispose: () => void } | null>(null);

  const handleMount: OnMount = (editor) => {
    if (handleRef) {
      handleRef.current = {
        undo: () => editor.trigger('canvas', 'undo', null),
        redo: () => editor.trigger('canvas', 'redo', null),
      };
    }
    selectionSub.current?.dispose();
    selectionSub.current = editor.onDidChangeCursorSelection((e) => {
      if (!onSelectionChange) return;
      const model = editor.getModel();
      if (!model || e.selection.isEmpty()) { onSelectionChange(null); return; }
      const start = model.getOffsetAt(e.selection.getStartPosition());
      const end = model.getOffsetAt(e.selection.getEndPosition());
      onSelectionChange({ start, end, text: model.getValueInRange(e.selection) });
    });
  };

  const handleChange: OnChange = (value) => onChange(value ?? '');

  return (
    <div className="min-h-[50vh] flex-1 overflow-hidden rounded-lg glass-card-subtle">
      <Editor
        height="100%"
        language={monacoLanguage(language)}
        value={content}
        theme="vs-dark"
        onChange={handleChange}
        onMount={handleMount}
        options={{
          readOnly: !editable,
          fontSize: 13,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          smoothScrolling: true,
          wordWrap: 'on',
          automaticLayout: true,
          padding: { top: 12, bottom: 12 },
        }}
      />
    </div>
  );
}
