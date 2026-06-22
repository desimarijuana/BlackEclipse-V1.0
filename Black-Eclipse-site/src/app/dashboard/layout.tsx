import { headers } from "next/headers"
import { redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import type { Metadata } from "next"
import { DashboardSidebar } from "@/components/layout/dashboard-sidebar"
import { prisma } from "@/lib/prisma"

export const metadata: Metadata = {
  title: "Dashboard — BlackEclipse",
}

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) {
    redirect("/login")
  }

  const dbUser = await prisma.user.findUnique({
    where: { id: session.user.id },
    select: { role: true },
  })
  const isAdmin = dbUser?.role === "admin"

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      <DashboardSidebar isAdmin={isAdmin} />
      <main className="flex-1 p-8 overflow-y-auto h-full scrollbar-thin">
        {children}
      </main>
    </div>
  )
}
