"use client"

import { useAuth } from "./auth-context"
import { useRouter } from "next/navigation"

export function SignOutButton() {
  const { logout } = useAuth()
  const router = useRouter()

  async function handleSignOut() {
    await logout()
    router.push("/login")
  }

  return (
    <button
      onClick={handleSignOut}
      className="w-full rounded-lg px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
    >
      Sign Out
    </button>
  )
}

