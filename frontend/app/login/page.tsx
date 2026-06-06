"use client"

import { Suspense, useState, useEffect } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { AuthForm } from "@/components/auth-form"
import { useAuthStore } from "@/store/authStore"
import { motion } from "framer-motion"
import { Play, Sparkles, Mic2, Zap, Film } from "lucide-react"

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] flex">
      {/* Left panel - product visual */}
      <div className="hidden lg:flex lg:w-1/2 relative items-center justify-center p-12" style={{ background: "linear-gradient(135deg, #111111 0%, #0a0a0a 100%)" }}>
        <div className="absolute inset-0" style={{ backgroundImage: "radial-gradient(circle at 30% 50%, rgba(255,87,34,0.08) 0%, transparent 60%)" }} />
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8 }}
          className="relative max-w-lg"
        >
          <div className="mb-12">
            <p className="eyebrow mb-4">Trusted by creators</p>
            <h2 className="text-[36px] font-semibold leading-tight tracking-[-0.025em] text-[#f5f4ef]" style={{ fontFamily: "var(--font-serif)" }}>
              From a 2-hour podcast to<span className="serif-italic text-[#ff5722]">6 viral clips</span> in under 90 seconds.
            </h2>
          </div>

          <div className="space-y-4">
            {[
              { icon: Sparkles, text: "AI finds the moments that hook your audience" },
              { icon: Mic2, text: "Speaker tracking keeps faces perfectly centered" },
              { icon: Zap, text: "Beat-synced cuts for maximum retention" },
              { icon: Film, text: "Render in 9:16, 1:1, 16:9 — all at once" },
            ].map((item, i) => (
              <motion.div
                key={item.text}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.5, delay: 0.3 + i * 0.1 }}
                className="flex items-center gap-4 rounded-xl p-4"
                style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg" style={{ background: "rgba(255,87,34,0.1)", border: "1px solid rgba(255,87,34,0.2)" }}>
                  <item.icon className="h-5 w-5 text-[#ff5722]" />
                </div>
                <span className="text-[14px] text-[#b8b6b0]">{item.text}</span>
              </motion.div>
            ))}
          </div>

          <div className="mt-10 flex items-center gap-3">
            <div className="flex -space-x-2">
              {["MR", "JC", "PS", "AK"].map((initials, i) => (
                <div
                  key={initials}
                  className="flex h-8 w-8 items-center justify-center rounded-full text-[10px] font-semibold text-[#0a0a0a] border-2 border-[#0a0a0a]"
                  style={{ background: i === 0 ? "#ff5722" : i === 1 ? "#ffb547" : i === 2 ? "#28c840" : "#4285F4", zIndex: 4 - i }}
                >
                  {initials}
                </div>
              ))}
            </div>
            <span className="text-[13px] text-[#8a8880]">Join<span className="font-semibold text-[#f5f4ef]">2,400+</span> creators</span>
          </div>
        </motion.div>
      </div>

      {/* Right panel - form */}
      <div className="flex flex-1 items-center justify-center p-4 lg:p-12">
        <div className="w-full max-w-md">
          <Suspense>
            <AuthFormInner />
          </Suspense>
        </div>
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
    <AuthForm
      mode="login"
      onSubmit={handleSubmit}
      isLoading={isLoading}
      error={error}
      googleLoading={googleLoading}
      onGoogleSignIn={handleGoogleSignIn}
    />
  )
}