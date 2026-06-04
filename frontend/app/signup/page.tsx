"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { AuthForm } from "@/components/auth-form"
import { useAuthStore } from "@/store/authStore"

export default function SignupPage() {
  const router = useRouter()
  const setUser = useAuthStore((s) => s.setUser)
  const [isLoading, setIsLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (data: { email: string; password: string; name?: string }) => {
    setIsLoading(true)
    setError(null)

    try {
      const res = await fetch("/api/auth/signup", {
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

      router.push("/?just_signed_up=true")
    } catch {
      setError("Failed to connect. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  const handleGoogleSignIn = () => {
    setGoogleLoading(true)
    window.location.href = "/api/auth/google?mode=signup"
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <AuthForm
          mode="signup"
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