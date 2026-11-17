'use client';

// ─── Canvas document editor (Tiptap, Markdown canonical) ──────────────────────
// Loaded through `next/dynamic` with `ssr: false` so Tiptap/ProseMirror never
// touch the server. Markdown is the source of truth: content is parsed in via
// the `@tiptap/markdown` extension and serialized back out on every update.

import { useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from 'react';
import { promptDialog } from '@/lib/ui/confirm-dialog';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from '@tiptap/markdown';
import Link from '@tiptap/extension-link';
import Placeholder from '@tiptap/extension-placeholder';
import { Table } from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';
import Image from '@tiptap/extension-image';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import { common, createLowlight } from 'lowlight';
import { Link2, List, ListChecks, Redo2, SquareCode, Table2, Undo2 } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { CanvasEditorHandle, CanvasSelection } from './canvas-utils';

const lowlight = createLowlight(common);

export interface DocumentEditorProps {
  content: string;
  editable?: boolean;
  docKey: string;
  onChange: (markdown: string) => void;
  onSelectionChange?: (selection: CanvasSelection | null) => void;
  handleRef?: MutableRefObject<CanvasEditorHandle | null>;
}

function ToolButton({
  label, active, disabled, onClick, children,
}: {
  label: string; active?: boolean; disabled?: boolean; onClick: () => void; children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'glass-card-subtle rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40',
        active && 'text-foreground bg-white/10',
      )}
    >
      {children}
    </button>
  );
}

export default function DocumentEditor({
  content, editable = true, docKey, onChange, onSelectionChange, handleRef,
}: DocumentEditorProps) {
  const [sourceMode, setSourceMode] = useState(false);
  const lastRendered = useRef(content);

  const extensions = useMemo(
    () => [
      StarterKit.configure({ codeBlock: false }),
      Markdown,
      Link.configure({ openOnClick: false, autolink: true }),
      Placeholder.configure({ placeholder: 'Start writing…' }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
      Image,
      CodeBlockLowlight.configure({ lowlight }),
    ],
    [],
  );

  const editor = useEditor({
    extensions,
    content,
    contentType: 'markdown',
    editable,
    immediatelyRender: false,
    onUpdate: ({ editor: ed }) => {
      const md = ed.getMarkdown();
      lastRendered.current = md;
      onChange(md);
    },
    onSelectionUpdate: ({ editor: ed }) => {
      const { from, to } = ed.state.selection;
      onSelectionChange?.(
        from !== to ? { start: from, end: to, text: ed.state.doc.textBetween(from, to, ' ') } : null,
      );
    },
  });

  // Reload the document when a new artifact/version is loaded.
  useEffect(() => {
    if (!editor) return;
    const incoming = content;
    if (incoming === lastRendered.current) return;
    lastRendered.current = incoming;
    editor.commands.setContent(incoming, { contentType: 'markdown', emitUpdate: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editor, docKey]);

  useEffect(() => {
    if (!handleRef) return;
    handleRef.current = {
      undo: () => editor?.chain().focus().undo().run(),
      redo: () => editor?.chain().focus().redo().run(),
    };
    return () => { handleRef.current = null; };
  }, [editor, handleRef]);

  if (!editor) {
    return <div className="flex-1 animate-pulse rounded-lg bg-white/5" aria-hidden />;
  }

  const setLink = async () => {
    const previous = editor.getAttributes('link').href as string | undefined;
    const url = await promptDialog({ title: 'Link URL', defaultValue: previous ?? 'https://', inputType: 'url' });
    if (url === null) return;
    if (url === '') editor.chain().focus().extendMarkRange('link').unsetLink().run();
    else editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run();
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-1 pb-2">
        <ToolButton label="Undo" disabled={!editable} onClick={() => editor.chain().focus().undo().run()}><Undo2 className="h-3.5 w-3.5" /></ToolButton>
        <ToolButton label="Redo" disabled={!editable} onClick={() => editor.chain().focus().redo().run()}><Redo2 className="h-3.5 w-3.5" /></ToolButton>
        <span className="mx-1 h-4 w-px bg-white/10" />
        <ToolButton label="Bold" active={editor.isActive('bold')} disabled={!editable} onClick={() => editor.chain().focus().toggleBold().run()}><span className="font-bold">B</span></ToolButton>
        <ToolButton label="Italic" active={editor.isActive('italic')} disabled={!editable} onClick={() => editor.chain().focus().toggleItalic().run()}><span className="italic">I</span></ToolButton>
        <ToolButton label="Heading 2" active={editor.isActive('heading', { level: 2 })} disabled={!editable} onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}>H2</ToolButton>
        <ToolButton label="Heading 3" active={editor.isActive('heading', { level: 3 })} disabled={!editable} onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}>H3</ToolButton>
        <ToolButton label="Bullet list" active={editor.isActive('bulletList')} disabled={!editable} onClick={() => editor.chain().focus().toggleBulletList().run()}><List className="h-3.5 w-3.5" /></ToolButton>
        <ToolButton label="Ordered list" active={editor.isActive('orderedList')} disabled={!editable} onClick={() => editor.chain().focus().toggleOrderedList().run()}><ListChecks className="h-3.5 w-3.5" /></ToolButton>
        <ToolButton label="Link" active={editor.isActive('link')} disabled={!editable} onClick={setLink}><Link2 className="h-3.5 w-3.5" /></ToolButton>
        <ToolButton label="Table" disabled={!editable} onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}><Table2 className="h-3.5 w-3.5" /></ToolButton>
        <ToolButton label="Code block" active={editor.isActive('codeBlock')} disabled={!editable} onClick={() => editor.chain().focus().toggleCodeBlock().run()}><SquareCode className="h-3.5 w-3.5" /></ToolButton>
        <button
          type="button"
          onClick={() => setSourceMode((v) => !v)}
          className="ml-auto glass-card-subtle rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
        >
          {sourceMode ? 'Rich text' : 'Markdown source'}
        </button>
      </div>

      {sourceMode ? (
        <textarea
          aria-label="Markdown source"
          value={content}
          readOnly={!editable}
          onChange={(e) => { lastRendered.current = e.target.value; onChange(e.target.value); }}
          spellCheck={false}
          className="min-h-[40vh] flex-1 resize-none rounded-lg glass-card-subtle p-3 font-mono text-[13px] leading-relaxed text-foreground/90 outline-none"
        />
      ) : (
        <div className={cn(
          'canvas-prose min-h-[40vh] flex-1 overflow-y-auto rounded-lg glass-card-subtle p-4 text-sm text-foreground/90',
          !editable && 'opacity-80',
        )}>
          <EditorContent editor={editor} />
        </div>
      )}
    </div>
  );
}
