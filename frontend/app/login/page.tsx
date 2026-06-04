"use client"

import { Suspense, useState, useEffect } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { AuthForm } from "@/components/auth-form"
import { useAuthStore } from "@/store/authStore"

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <Suspense>
          <AuthFormInner />
        </Suspense>
      </div>
    </div>
  )
}

function AuthFormInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const setUser = useAuthStore((s) => s.setUser)
  const [isLoading, setIsLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const googleError = searchParams.get("google_error")
    if (googleError) {
      setError("Google sign-in failed. Please try again.")
      window.history.replaceState({}, "", "/login")
    }
  }, [searchParams])

  const handleSubmit = async (data: { email: string; password: string }) => {
    setIsLoading(true)
    setError(null)

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      })

      const json = await res.json()

      if (!res.ok) {
        setError(json.error || "Something went wrong")
        return
      }

      if (json.accessToken) {
        setUser(json.user, json.accessToken)
      } else {
        setUser(json.user)
      }

      router.push("/?just_logged_in=true")
    } catch {
      setError("Failed to connect. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  const handleGoogleSignIn = () => {
    setGoogleLoading(true)
    window.location.href = "/api/auth/google?mode=login"
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <AuthForm
          mode="login"
          onSubmit={handleSubmit}
          isLoading={isLoading}
          error={error}
          googleLoading={googleLoading}
          onGoogleSignIn={handleGoogleSignIn}
        />
      </div>
    </div>
  )
}