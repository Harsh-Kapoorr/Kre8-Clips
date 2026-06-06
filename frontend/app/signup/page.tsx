"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { AuthForm } from "@/components/auth-form"
import { useAuthStore } from "@/store/authStore"
import { motion } from "framer-motion"
import { Sparkles, Mic2, Zap, Film, Clock } from "lucide-react"

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
    <div className="min-h-screen bg-[#0a0a0a] flex">
      {/* Left panel - product visual */}
      <div className="hidden lg:flex lg:w-1/2 relative items-center justify-center p-12" style={{ background: "linear-gradient(135deg, #111111 0%, #0a0a0a 100%)" }}>
        <div className="absolute inset-0" style={{ backgroundImage: "radial-gradient(circle at 70% 50%, rgba(255,87,34,0.1) 0%, transparent 60%)" }} />
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8 }}
          className="relative max-w-lg"
        >
          <div className="mb-12">
            <p className="eyebrow mb-4">Start free today</p>
            <h2 className="text-[36px] font-semibold leading-tight tracking-[-0.025em] text-[#f5f4ef]" style={{ fontFamily: "var(--font-serif)" }}>
              Your first<span className="serif-italic text-[#ff5722]"> viral clip</span> is90 seconds away.
            </h2>
          </div>

          <div className="space-y-4">
            {[
              { icon: Clock, text: "1 free clip when you sign up — no credit card" },
              { icon: Sparkles, text: "AI finds hooks, builds narratives, renders clips" },
              { icon: Mic2, text: "Speaker tracking + beat sync + captions included" },
              { icon: Zap, text: "Up to 3 clips per video on the free plan" },
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

          <div className="mt-10 rounded-xl p-5" style={{ background: "rgba(255,87,34,0.06)", border: "1px solid rgba(255,87,34,0.15)" }}>
            <p className="text-[14px] text-[#b8b6b0]">
              <span className="font-semibold text-[#f5f4ef]">"I dropped in a 2-hour podcast and got six ready-to-post clips in under two minutes."</span>
              <br />
              <span className="mt-2 block text-[12px] text-[#8a8880]">— Maya Reyes, Creator · 240k followers</span>
</p>
          </div>
        </motion.div>
      </div>

      {/* Right panel - form */}
      <div className="flex flex-1 items-center justify-center p-4 lg:p-12">
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
    </div>
  )
}