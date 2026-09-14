"use client";

// ── Settings › Sidebar ────────────────────────────────────────────────────
// Lets the user customize the primary navigation menu: reorder items (drag or
// arrow buttons), assign an F-key to open them instantly, and enable/disable
// items. Everything reads/writes the shared sidebar store, so changes apply to
// the live sidebar immediately.

import { useState } from 'react';
import {
  PanelLeft, GripVertical, ArrowUp, ArrowDown, RotateCcw, Sparkles, Keyboard, EyeOff,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DEFAULT_SIDEBAR_SECTIONS, SHORTCUT_OPTIONS, type SidebarSectionDef } from '@/lib/sidebar/config';
import { useSidebarConfigStore } from '@/lib/sidebar/store';
import type { AppTab } from '@/components/layout/sidebar';

const DEF_BY_ID = new Map<string, SidebarSectionDef>(DEFAULT_SIDEBAR_SECTIONS.map((s) => [s.id, s]));

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center border rounded-full transition-colors cursor-pointer",
        checked ? "bg-primary/25 border-primary/50" : "bg-muted/60 border-border"
      )}
    >
      <span
        className={cn(
          "inline-block h-3.5 w-3.5 transform rounded-full shadow-sm transition-transform",
          checked ? "translate-x-[18px] bg-primary" : "translate-x-[2px] bg-muted-foreground/70"
        )}
      />
    </button>
  );
}

export function SidebarSettingsPanel() {
  const config = useSidebarConfigStore((s) => s.config);
  const toggleEnabled = useSidebarConfigStore((s) => s.toggleEnabled);
  const setShortcut = useSidebarConfigStore((s) => s.setShortcut);
  const move = useSidebarConfigStore((s) => s.move);
  const reset = useSidebarConfigStore((s) => s.reset);

  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);

  const handleDrop = (toIndex: number) => {
    if (dragIndex !== null) move(dragIndex, toIndex);
    setDragIndex(null);
    setOverIndex(null);
  };

  // Shortcuts already taken — shown as disabled options in the other rows.
  const usedShortcuts = new Set(config.sections.filter((s) => s.shortcut).map((s) => s.shortcut));

  return (
    <div className="animate-fade-in-up">
      <div className="mb-6">
        <p className="text-[10px] uppercase tracking-[0.2em] text-primary font-bold mb-2 flex items-center gap-1.5">
          <Sparkles size={11} /> Navigate
        </p>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 shadow-sm shadow-primary/10">
            <PanelLeft className="text-primary w-[18px] h-[18px]" />
          </div>
          <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">Sidebar Menu</h2>
        </div>
        <p className="text-xs text-muted-foreground mt-2 leading-relaxed max-w-lg">
          Reorder the navigation menu, hide items you don&apos;t use, and assign an F-key to jump straight to a screen.
        </p>
      </div>

      <div className="rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden">
        <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-border/10">
          <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">
            {config.sections.length} items
          </span>
          <Button
            variant="outline"
            size="sm"
            className="cursor-pointer rounded-xl"
            onClick={reset}
          >
            <RotateCcw className="w-3.5 h-3.5 mr-1" /> Reset to default
          </Button>
        </div>

        <div className="p-2 sm:p-3 space-y-1.5">
          {config.sections.map((section, index) => {
            const def = DEF_BY_ID.get(section.id);
            if (!def) return null;
            const Icon = def.icon;
            const isDragging = dragIndex === index;
            const isOver = overIndex === index && dragIndex !== null && dragIndex !== index;
            return (
              <div
                key={section.id}
                draggable
                onDragStart={() => setDragIndex(index)}
                onDragEnd={() => { setDragIndex(null); setOverIndex(null); }}
                onDragOver={(e) => { e.preventDefault(); setOverIndex(index); }}
                onDrop={(e) => { e.preventDefault(); handleDrop(index); }}
                className={cn(
                  "flex items-center gap-2 sm:gap-3 px-2.5 sm:px-3 py-2.5 rounded-xl border transition-all",
                  isDragging
                    ? "opacity-50 border-primary/40 bg-primary/5"
                    : isOver
                    ? "border-primary/40 bg-primary/5"
                    : "border-border/20 glass-card-subtle hover:border-border/40",
                  !section.enabled && "opacity-60"
                )}
              >
                <span className="cursor-grab active:cursor-grabbing text-muted-foreground/60 hover:text-foreground shrink-0" title="Drag to reorder">
                  <GripVertical size={15} />
                </span>

                <span className={cn(
                  "w-8 h-8 rounded-lg border flex items-center justify-center shrink-0",
                  section.enabled ? "border-primary/20 bg-primary/10" : "border-border/30 bg-muted/20"
                )}>
                  <Icon size={15} className={section.enabled ? "text-primary" : "text-muted-foreground"} />
                </span>

                <div className="flex flex-col min-w-0 flex-1">
                  <span className="text-xs font-semibold text-foreground truncate">{def.label}</span>
                  <span className="text-[9px] text-muted-foreground tracking-wide truncate">{section.id}</span>
                </div>

                {/* Shortcut assignment */}
                <div className="hidden sm:flex items-center gap-1.5 shrink-0">
                  <Keyboard size={13} className="text-muted-foreground" />
                  <Select
                    value={section.shortcut || "__none__"}
                    onValueChange={(v) => setShortcut(section.id as AppTab, v === "__none__" ? "" : v ?? "")}
                  >
                    <SelectTrigger className="h-7 w-[76px] text-[10px] rounded-lg">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SHORTCUT_OPTIONS.map((opt) => {
                        const takenByOther = opt.value !== "" && opt.value !== section.shortcut && usedShortcuts.has(opt.value);
                        return (
                          <SelectItem
                            key={opt.value || "__none__"}
                            value={opt.value || "__none__"}
                            disabled={takenByOther}
                          >
                            {opt.value === "" ? "None" : `${opt.label}${takenByOther ? " (used)" : ""}`}
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                </div>

                {/* Reorder fallback buttons */}
                <div className="flex items-center gap-0.5 shrink-0">
                  <button
                    onClick={() => move(index, index - 1)}
                    disabled={index === 0}
                    className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-30 disabled:pointer-events-none cursor-pointer"
                    title="Move up"
                  >
                    <ArrowUp size={13} />
                  </button>
                  <button
                    onClick={() => move(index, index + 1)}
                    disabled={index === config.sections.length - 1}
                    className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-30 disabled:pointer-events-none cursor-pointer"
                    title="Move down"
                  >
                    <ArrowDown size={13} />
                  </button>
                </div>

                <span className="shrink-0 flex items-center gap-2">
                  {!section.enabled && <EyeOff size={12} className="text-muted-foreground hidden sm:block" />}
                  <Toggle
                    checked={section.enabled}
                    onChange={() => toggleEnabled(section.id as AppTab)}
                  />
                </span>
              </div>
            );
          })}
        </div>

        <p className="text-[10px] text-muted-foreground px-5 py-3.5 border-t border-border/10 flex items-center gap-1.5">
          <Keyboard size={11} /> Shortcuts work anywhere in the app. Hidden items stay in this list but leave the sidebar.
        </p>
      </div>
    </div>
  );
}
