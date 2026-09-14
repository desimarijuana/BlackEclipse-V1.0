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
import {
  DndContext, DragOverlay, PointerSensor, KeyboardSensor, useSensor, useSensors,
  closestCenter, type DragStartEvent, type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext, verticalListSortingStrategy, useSortable, sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

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

  const [activeId, setActiveId] = useState<AppTab | null>(null);

  // Pointer + keyboard sensors: the drag owns the pointer (so the modal's own
  // scroll/click handling never swallows it) and is reachable by keyboard.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragStart = (e: DragStartEvent) => setActiveId(e.active.id as AppTab);

  const handleDragEnd = (e: DragEndEvent) => {
    setActiveId(null);
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const from = config.sections.findIndex((s) => s.id === active.id);
    const to = config.sections.findIndex((s) => s.id === over.id);
    if (from === -1 || to === -1) return;
    move(from, to);
  };

  // Shortcuts already taken — shown as disabled options in the other rows.
  const usedShortcuts = new Set(config.sections.filter((s) => s.shortcut).map((s) => s.shortcut));
  const sortableIds = config.sections.map((s) => s.id);

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

        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
          onDragCancel={() => setActiveId(null)}
        >
          <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
            <div className="p-2 sm:p-3 space-y-1.5">
              {config.sections.map((section, index) => {
                const def = DEF_BY_ID.get(section.id);
                if (!def) return null;
                return (
                  <SortableRow
                    key={section.id}
                    def={def}
                    id={section.id as AppTab}
                    enabled={section.enabled}
                    canMoveUp={index > 0}
                    canMoveDown={index < config.sections.length - 1}
                    shortcut={section.shortcut}
                    usedShortcuts={usedShortcuts}
                    onToggle={() => toggleEnabled(section.id as AppTab)}
                    onShortcut={(v) => setShortcut(section.id as AppTab, v)}
                    onMoveUp={() => move(index, index - 1)}
                    onMoveDown={() => move(index, index + 1)}
                  />
                );
              })}
            </div>
          </SortableContext>

          <DragOverlay dropAnimation={{ duration: 200, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' }}>
            {activeId ? (
              <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl border border-primary/40 bg-popover glass-card-strong shadow-2xl shadow-black/50 rotate-[1.5deg] pointer-events-none">
                <GripVertical size={15} className="text-primary shrink-0" />
                <span className="text-xs font-semibold text-foreground truncate">
                  {DEF_BY_ID.get(activeId)?.label ?? activeId}
                </span>
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>

        <p className="text-[10px] text-muted-foreground px-5 py-3.5 border-t border-border/10 flex items-center gap-1.5">
          <Keyboard size={11} /> Shortcuts work anywhere in the app. Hidden items stay in this list but leave the sidebar.
        </p>
      </div>
    </div>
  );
}

interface SortableRowProps {
  def: SidebarSectionDef;
  id: AppTab;
  enabled: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  shortcut: string;
  usedShortcuts: Set<string>;
  onToggle: () => void;
  onShortcut: (v: string) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

function SortableRow({
  def, id, enabled, canMoveUp, canMoveDown, shortcut, usedShortcuts,
  onToggle, onShortcut, onMoveUp, onMoveDown,
}: SortableRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const Icon = def.icon;

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "flex items-center gap-2 sm:gap-3 px-2.5 sm:px-3 py-2.5 rounded-xl border transition-all",
        isDragging
          ? "opacity-40 border-primary/40 bg-primary/5"
          : "border-border/20 glass-card-subtle hover:border-border/40",
        !enabled && "opacity-60"
      )}
    >
      <span
        {...attributes}
        {...listeners}
        className="shrink-0 touch-none select-none cursor-grab active:cursor-grabbing text-muted-foreground/60 hover:text-foreground"
        title="Drag to reorder"
      >
        <GripVertical size={15} />
      </span>

      <span className={cn(
        "w-8 h-8 rounded-lg border flex items-center justify-center shrink-0",
        enabled ? "border-primary/20 bg-primary/10" : "border-border/30 bg-muted/20"
      )}>
        <Icon size={15} className={enabled ? "text-primary" : "text-muted-foreground"} />
      </span>

      <div className="flex flex-col min-w-0 flex-1">
        <span className="text-xs font-semibold text-foreground truncate">{def.label}</span>
        <span className="text-[9px] text-muted-foreground tracking-wide truncate">{id}</span>
      </div>

      {/* Shortcut assignment */}
      <div className="hidden sm:flex items-center gap-1.5 shrink-0">
        <Keyboard size={13} className="text-muted-foreground" />
        <Select
          value={shortcut || "__none__"}
          onValueChange={(v) => onShortcut(v === "__none__" ? "" : v ?? "")}
        >
          <SelectTrigger className="h-7 w-[76px] text-[10px] rounded-lg">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SHORTCUT_OPTIONS.map((opt) => {
              const takenByOther = opt.value !== "" && opt.value !== shortcut && usedShortcuts.has(opt.value);
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
          onClick={onMoveUp}
          disabled={!canMoveUp}
          className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-30 disabled:pointer-events-none cursor-pointer"
          title="Move up"
        >
          <ArrowUp size={13} />
        </button>
        <button
          onClick={onMoveDown}
          disabled={!canMoveDown}
          className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-30 disabled:pointer-events-none cursor-pointer"
          title="Move down"
        >
          <ArrowDown size={13} />
        </button>
      </div>

      <span className="shrink-0 flex items-center gap-2">
        {!enabled && <EyeOff size={12} className="text-muted-foreground hidden sm:block" />}
        <Toggle checked={enabled} onChange={onToggle} />
      </span>
    </div>
  );
}
