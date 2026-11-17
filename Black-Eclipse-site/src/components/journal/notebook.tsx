'use client';

// ── Journal Notebook — free-form written journal (Phase 5) ────────────────────
// Standalone entries not tied to a day or trade: lessons, market thesis, mental
// notes. Backed by the JournalEntry model. Kept deliberately simple.

import React, { useCallback, useEffect, useState } from 'react';
import { confirmDialog } from '@/lib/ui/confirm-dialog';
import { Plus, Trash2, StickyNote } from '@/lib/icons';
import { cn } from '@/lib/utils';

interface Entry { id: string; title: string; body: string; createdAt: string; updatedAt: string }

export function JournalNotebook() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/journal/entries');
      const data = await res.json();
      setEntries(data.entries ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const create = async () => {
    if (!title.trim() && !body.trim()) return;
    setSaving(true);
    try {
      await fetch('/api/journal/entries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, body }),
      });
      setTitle('');
      setBody('');
      await load();
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: string) => {
    if (!(await confirmDialog({ title: 'Delete this entry?', tone: 'danger' }))) return;
    await fetch(`/api/journal/entries/${id}`, { method: 'DELETE' });
    await load();
  };

  const inputCls = 'w-full rounded-lg bg-background/60 border border-border/40 hover:border-primary/50 px-3 py-2 text-xs font-mono focus:ring-1 focus:ring-primary outline-none transition-colors';

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="font-serif text-lg font-semibold text-foreground flex items-center gap-2"><StickyNote size={16} className="text-primary" /> Notebook</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Free-form journal — lessons, thesis, mental state. Not tied to a trade or day.</p>
      </div>

      <div className="rounded-2xl glass-card p-4">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" className={cn(inputCls, 'font-sans')} />
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={4}
          placeholder="Write…"
          className={cn(inputCls, 'mt-2 resize-y font-sans')}
        />
        <div className="mt-3 flex justify-end">
          <button
            onClick={() => void create()}
            disabled={saving || (!title.trim() && !body.trim())}
            className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-4 py-2 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
          >
            {saving ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary/30 border-t-primary" /> : <Plus size={13} />} Add entry
          </button>
        </div>
      </div>

      {loading ? (
        <div className="rounded-2xl glass-card p-8 flex justify-center">
          <span className="h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
        </div>
      ) : entries.length === 0 ? (
        <div className="rounded-2xl glass-card p-8 text-center">
          <p className="text-xs text-muted-foreground italic">No entries yet. Start writing above.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {entries.map((e) => (
            <div key={e.id} className="rounded-2xl glass-card p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="font-serif text-sm font-semibold text-foreground truncate">{e.title || 'Untitled'}</h3>
                  <p className="font-mono text-[10px] text-muted-foreground">{new Date(e.createdAt).toLocaleString()}</p>
                </div>
                <button onClick={() => void remove(e.id)} className="text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer shrink-0" title="Delete">
                  <Trash2 size={13} />
                </button>
              </div>
              {e.body && <p className="mt-2 whitespace-pre-wrap text-xs text-muted-foreground leading-relaxed">{e.body}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
