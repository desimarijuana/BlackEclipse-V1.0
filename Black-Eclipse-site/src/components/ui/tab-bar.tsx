"use client"

import React from "react"
import { cn } from "@/lib/utils"

export interface TabItem {
  id: string
  label: React.ReactNode
  icon?: React.ComponentType<{ size?: number; className?: string }>
  badge?: React.ReactNode
  /** Override the active state (e.g. sub-tabs that share a parent id). */
  active?: boolean
}

interface TabBarProps {
  items: TabItem[]
  activeId?: string
  onChange: (id: string) => void
  className?: string
  leading?: React.ReactNode
  trailing?: React.ReactNode
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
}: TabBarProps) {
  return (
    <div
      className={cn(
        "tab-bar-glass mb-5 flex items-center gap-2 p-1.5 rounded-3xl shrink-0 overflow-x-auto scrollbar-hide",
        className
      )}
    >
      {leading}
      {items.map((item) => {
        const Icon = item.icon
        const active = item.active ?? item.id === activeId
        return (
          <button
            key={item.id}
            onClick={() => onChange(item.id)}
            aria-pressed={active}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 rounded-2xl text-xs font-bold transition-all cursor-pointer whitespace-nowrap shrink-0",
              active
                ? "bg-primary/15 text-primary"
                : "bg-accent/30 text-muted-foreground hover:text-foreground hover:bg-accent/60"
            )}
          >
            {Icon && <Icon size={12} />}
            {item.label}
            {item.badge}
          </button>
        )
      })}
      {trailing}
    </div>
  )
}
