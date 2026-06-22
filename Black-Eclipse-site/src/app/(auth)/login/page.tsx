import Link from "next/link"
import { Brain } from "lucide-react"
import { LoginForm } from "@/components/auth/login-form"

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <Link href="/" className="inline-flex items-center gap-2">
            <Brain className="h-6 w-6 text-primary" />
            <span className="font-mono text-lg font-semibold tracking-tight">
              BlackEclipse
            </span>
          </Link>
          <h1 className="mt-6 font-serif text-2xl">Welcome back</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Sign in to your research dashboard
          </p>
        </div>
        <LoginForm />
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-primary hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  )
}
