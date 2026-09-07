'use client';

// ── WorkspaceDrawer — add-widget palette, templates, reset ───────────────────
// Fixed side drawer (frosted glass) so opening it never pushes the canvas.
// Confirm dialogs guard template apply and reset.

import React, { useState } from 'react';
import { LayoutTemplate, Plus, RotateCcw, X } from 'lucide-react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import type { WorkspaceController } from './use-workspace';

export interface WorkspaceWidgetMeta {
  widgetId: string;
  label: string;
  desc: string;
}

interface WorkspaceDrawerProps {
  onClose: () => void;
  workspace: WorkspaceController;
  widgets: WorkspaceWidgetMeta[];
}

export function WorkspaceDrawer({ onClose, workspace, widgets }: WorkspaceDrawerProps) {
  const { ops, templates, layout } = workspace;
  const [confirm, setConfirm] = useState<{ kind: 'template' | 'reset'; templateId?: string } | null>(null);
  const placed = new Set(layout.sections.flatMap(s => s.columns.flatMap(c => c.widgets.map(w => w.widgetId))));

  return (
    <>
      <div className="fixed inset-0 z-40 flex justify-end animate-fade-in" data-nodrag>
        <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
        <aside className="relative flex w-80 max-w-[85vw] flex-col h-full border-l border-white/15 dark:border-white/10 bg-[#0f0f0f]/85 dark:bg-[#0f0f0f]/85 bg-white/85 backdrop-blur-2xl shadow-2xl shadow-black/40 animate-slide-in">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/10">
            <span className="font-serif text-sm font-semibold text-foreground">Customize workspace</span>
            <button onClick={onClose} className="rounded-lg p-1 text-muted-foreground hover:text-foreground hover:bg-accent cursor-pointer">
              <X size={14} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto scrollbar-hide p-4 flex flex-col gap-5">
            {/* Widgets palette */}
            <section>
              <h4 className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground mb-2">Add widget</h4>
              <div className="flex flex-col gap-1.5">
                {widgets.map((w) => (
                  <button
                    key={w.widgetId}
                    onClick={() => ops.addWidget(w.widgetId)}
                    className="group flex items-start gap-2 rounded-xl border border-border/30 bg-accent/20 hover:bg-accent/50 hover:border-primary/40 px-3 py-2.5 text-left transition-all cursor-pointer"
                  >
                    <Plus size={13} className="mt-0.5 shrink-0 text-muted-foreground group-hover:text-primary transition-colors" />
                    <span className="min-w-0">
                      <span className="block text-xs font-bold text-foreground">
                        {w.label}
                        {placed.has(w.widgetId) && <span className="ml-1.5 text-[9px] font-mono text-emerald-400">placed</span>}
                      </span>
                      <span className="block text-[10px] text-muted-foreground leading-snug">{w.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
            </section>

            {/* Templates */}
            <section>
              <h4 className="flex items-center gap-1.5 text-[9px] uppercase tracking-widest font-bold text-muted-foreground mb-2">
                <LayoutTemplate size={11} /> Templates
              </h4>
              <div className="flex flex-col gap-1.5">
                {templates.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setConfirm({ kind: 'template', templateId: t.id })}
                    className="rounded-xl border border-border/30 bg-accent/20 hover:bg-accent/50 hover:border-primary/40 px-3 py-2.5 text-left transition-all cursor-pointer"
                  >
                    <span className="block text-xs font-bold text-foreground">{t.name}</span>
                    <span className="block text-[10px] text-muted-foreground leading-snug">{t.desc}</span>
                  </button>
                ))}
              </div>
            </section>

            {/* Reset */}
            <section>
              <button
                onClick={() => setConfirm({ kind: 'reset' })}
                className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-rose-500/20 bg-rose-500/5 hover:bg-rose-500/10 px-3 py-2.5 text-xs font-bold text-rose-400 transition-all cursor-pointer"
              >
                <RotateCcw size={12} /> Reset to default layout
              </button>
            </section>
          </div>
        </aside>
      </div>

      <Dialog open={confirm !== null} onOpenChange={(o) => { if (!o) setConfirm(null); }}>
        <DialogContent className="max-w-sm rounded-2xl border border-white/15 dark:border-white/10 bg-[#0f0f0f]/85 dark:bg-[#0f0f0f]/85 bg-white/85 backdrop-blur-2xl">
          <DialogTitle className="sr-only">Confirm</DialogTitle>
          <h3 className="font-serif text-base text-foreground">
            {confirm?.kind === 'reset' ? 'Reset layout?' : 'Replace current layout?'}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {confirm?.kind === 'reset'
              ? 'Your custom arrangement for this workspace will be cleared and the default restored.'
              : 'Applying a template replaces your current custom layout. This cannot be undone.'}
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <button
              onClick={() => setConfirm(null)}
              className="rounded-xl border border-border/40 bg-accent/30 hover:bg-accent/60 px-3 py-2 text-xs font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer"
            >Cancel</button>
            <button
              onClick={() => {
                if (confirm?.kind === 'reset') ops.resetToDefault();
                else if (confirm?.kind === 'template') {
                  const t = templates.find(x => x.id === confirm.templateId);
                  if (t) ops.applyTemplate(t);
                }
                setConfirm(null);
              }}
              className={cn(
                'rounded-xl px-3 py-2 text-xs font-bold transition-all cursor-pointer border',
                'border-rose-500/30 bg-rose-500/10 text-rose-400 hover:bg-rose-500/20',
              )}
            >Replace</button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}