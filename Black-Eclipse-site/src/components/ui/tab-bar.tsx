"use client"

import React from "react"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

export interface TabItem {
  id: string
  label: React.ReactNode
  icon?: React.ComponentType<{ size?: number; className?: string }>
  badge?: React.ReactNode
  /** Override the active state (e.g. sub-tabs that share a parent id). */
  active?: boolean
  /** Render as a non-button container (e.g. an inline rename input). */
  editing?: boolean
}

interface TabBarProps {
  items: TabItem[]
  activeId?: string
  onChange: (id: string) => void
  className?: string
  leading?: React.ReactNode
  trailing?: React.ReactNode
  /** Double-clicking a tab (e.g. to start a rename). */
  onItemDoubleClick?: (id: string) => void
  /** When provided, each tab shows a remove affordance. */
  onItemRemove?: (id: string) => void
  /**
   * Container weight. `glass` (default) is the heavy frosted strip; `subtle`
   * is the restrained control-strip tier for dense/toolbar-adjacent tab rows.
   */
  variant?: 'glass' | 'subtle'
}

/**
 * Frosted-glass tab strip — the unified tab style across the terminal.
 * Modeled on the portfolio fund tabs: a rounded glass container with
 * pill buttons that light up in primary when active.
 */
export function TabBar({
  items,
  activeId,
  onChange,
  className,
  leading,
  trailing,
  onItemDoubleClick,
  onItemRemove,
  variant = 'glass',
}: TabBarProps) {
  return (
    <div
      className={cn(
        'mb-5 flex items-center gap-1.5 p-1 rounded-2xl shrink-0 overflow-x-auto scrollbar-hide',
        variant === 'glass' ? 'tab-bar-glass' : 'tab-bar-subtle',
        className
      )}
    >
      {leading}
      {items.map((item) => {
        const Icon = item.icon
        const active = item.active ?? item.id === activeId
        const classNameForTab = cn(
          'group flex items-center gap-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer whitespace-nowrap shrink-0',
          variant === 'glass' ? 'px-4 py-2' : 'px-3 py-1.5',
          active
            ? 'bg-primary/15 text-primary'
            : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
        )

        if (item.editing) {
          return (
            <div key={item.id} className={classNameForTab} aria-pressed={active}>
              {item.label}
            </div>
          )
        }

        return (
          <button
            key={item.id}
            onClick={() => onChange(item.id)}
            onDoubleClick={onItemDoubleClick ? () => onItemDoubleClick(item.id) : undefined}
            aria-pressed={active}
            className={classNameForTab}
          >
            {Icon && <Icon size={12} />}
            {item.label}
            {item.badge}
            {onItemRemove && (
              <span
                role="button"
                tabIndex={-1}
                onClick={(e) => { e.stopPropagation(); onItemRemove(item.id); }}
                onDoubleClick={(e) => e.stopPropagation()}
                className="ml-0.5 -mr-1 cursor-pointer rounded-md p-0.5 text-muted-foreground/40 opacity-0 transition-opacity hover:text-rose-400 group-hover:opacity-100"
                title="Remove"
              >
                <X size={11} />
              </span>
            )}
          </button>
        )
      })}
      {trailing}
    </div>
  )
}
