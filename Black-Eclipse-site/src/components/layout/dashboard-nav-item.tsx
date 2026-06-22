import Link from "next/link"
import type { ComponentType } from "react"

export function DashboardNavItem({
  href,
  icon: Icon,
  label,
}: {
  href: string
  icon: ComponentType<{ className?: string }>
  label: string
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    >
      <Icon className="h-4 w-4" />
      {label}
    </Link>
  )
}
