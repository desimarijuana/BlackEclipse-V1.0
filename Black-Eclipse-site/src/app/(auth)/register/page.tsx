import Link from "next/link"
import { Brain } from "lucide-react"
import { RegisterForm } from "@/components/auth/register-form"

export default function RegisterPage() {
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
          <h1 className="mt-6 font-serif text-2xl">Create your account</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Start researching markets with AI
          </p>
        </div>
        <RegisterForm />
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link href="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
