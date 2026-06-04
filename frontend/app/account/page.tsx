"use client"

import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useAuthStore } from "@/store/authStore"
import { LockBanner } from "@/components/lock-banner"
import { PLANS, isLockedOut } from "@/lib/plans"
import { cn } from "@/lib/utils"

type Tab = "profile" | "apikeys" | "plan"

export default function AccountPage() {
  const { user } = useAuthStore()
  const [activeTab, setActiveTab] = useState<Tab>("profile")

  if (!user) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
        <p className="text-[#6a6860]">Please sign in to view your account.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <LockBanner />
      <div className="mx-auto max-w-4xl px-5 py-12 sm:px-8">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <h1 className="mb-8 text-[28px] font-semibold text-[#f5f4ef]">Account Settings</h1>

          <div className="mb-6 flex gap-1 rounded-lg border border-white/10 bg-white/5 p-1">
            {(["profile", "apikeys", "plan"] as Tab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={cn(
                  "flex-1 rounded-md px-4 py-2 text-[13px] font-medium transition-colors",
                  activeTab === tab
                    ? "bg-white/10 text-[#f5f4ef]"
                    : "text-[#6a6860] hover:text-[#b8b6b0]"
                )}
              >
                {tab === "profile" ? "Profile" : tab === "apikeys" ? "API Keys" : "Plan"}
              </button>
            ))}
          </div>

          <AnimatePresence mode="wait">
            {activeTab === "profile" && <ProfileTab user={user} />}
            {activeTab === "apikeys" && <ApiKeysTab user={user} />}
            {activeTab === "plan" && <PlanTab user={user} />}
          </AnimatePresence>
        </motion.div>
      </div>
    </div>
  )
}

function ProfileTab({ user }: { user: { name: string; email: string; plan: string } }) {
  const [name, setName] = useState(user.name)
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)

  const handleSave = async () => {
    setIsLoading(true)
    setMessage(null)
    try {
      const res = await fetch("/api/account/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      })
      if (res.ok) {
        setMessage({ type: "success", text: "Profile updated successfully." })
      } else {
        setMessage({ type: "error", text: "Failed to update profile." })
      }
    } catch {
      setMessage({ type: "error", text: "Something went wrong." })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <motion.div
      key="profile"
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 10 }}
      className="rounded-xl border border-white/5 bg-white/[0.02] p-6"
    >
      <h2 className="mb-6 text-[18px] font-medium text-[#f5f4ef]">Profile Information</h2>

      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-[13px] font-medium text-[#b8b6b0]">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-[14px] text-[#f5f4ef] placeholder:text-[#5a5858] focus:border-[#ff5722]/50 focus:outline-none focus:ring-1 focus:ring-[#ff5722]/25 transition-colors"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-[13px] font-medium text-[#b8b6b0]">Email</label>
          <input
            type="email"
            value={user.email}
            disabled
            className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-[14px] text-[#5a5858]"
          />
          <p className="mt-1 text-[12px] text-[#5a5858]">Email cannot be changed</p>
        </div>

        {message && (
          <div
            className={cn(
              "rounded-lg px-4 py-3 text-[13px]",
              message.type === "success"
                ? "bg-green-500/10 text-green-400"
                : "bg-red-500/10 text-red-400"
            )}
          >
            {message.text}
          </div>
        )}

        <button
          onClick={handleSave}
          disabled={isLoading}
          className="rounded-lg bg-[#ff5722] px-6 py-2.5 text-[14px] font-semibold text-[#0a0a0a] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isLoading ? "Saving..." : "Save changes"}
        </button>
      </div>
    </motion.div>
  )
}

function ApiKeysTab({ user }: { user: { id: string; plan: string } }) {
  const [deepgramKey, setDeepgramKey] = useState("")
  const [geminiKey, setGeminiKey] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)

  const handleSave = async () => {
    setIsLoading(true)
    setMessage(null)
    try {
      const res = await fetch("/api/account/keys", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deepgram_key: deepgramKey, gemini_key: geminiKey }),
      })
      if (res.ok) {
        setMessage({ type: "success", text: "API keys saved successfully." })
        setDeepgramKey("")
        setGeminiKey("")
      } else {
        const json = await res.json()
        setMessage({ type: "error", text: json.error || "Failed to save API keys." })
      }
    } catch {
      setMessage({ type: "error", text: "Something went wrong." })
    } finally {
      setIsLoading(false)
    }
  }

  if (user.plan !== "byok") {
    return (
      <motion.div
        key="apikeys"
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: 10 }}
        className="rounded-xl border border-white/5 bg-white/[0.02] p-6"
      >
        <div className="flex items-center gap-3 text-[#6a6860]">
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <p className="text-[14px]">
            API Keys are only available for the{" "}
            <a href="/pricing" className="text-[#ff5722] hover:underline">BYOK plan</a>.
          </p>
        </div>
      </motion.div>
    )
  }

  return (
    <motion.div
      key="apikeys"
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 10 }}
      className="rounded-xl border border-white/5 bg-white/[0.02] p-6"
    >
      <h2 className="mb-6 text-[18px] font-medium text-[#f5f4ef]">API Keys</h2>
      <p className="mb-6 text-[13px] text-[#6a6860]">
        Enter your Deepgram and Gemini API keys to enable advanced features. These are stored securely and only used when processing your videos.
      </p>

      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-[13px] font-medium text-[#b8b6b0]">Deepgram Key</label>
          <input
            type="password"
            value={deepgramKey}
            onChange={(e) => setDeepgramKey(e.target.value)}
            placeholder="sk_live_..."
            className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-[14px] text-[#f5f4ef] placeholder:text-[#5a5858] focus:border-[#ff5722]/50 focus:outline-none focus:ring-1 focus:ring-[#ff5722]/25 transition-colors"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-[13px] font-medium text-[#b8b6b0]">Gemini Key</label>
          <input
            type="password"
            value={geminiKey}
            onChange={(e) => setGeminiKey(e.target.value)}
            placeholder="AIza..."
            className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-[14px] text-[#f5f4ef] placeholder:text-[#5a5858] focus:border-[#ff5722]/50 focus:outline-none focus:ring-1 focus:ring-[#ff5722]/25 transition-colors"
          />
        </div>

        {message && (
          <div
            className={cn(
              "rounded-lg px-4 py-3 text-[13px]",
              message.type === "success"
                ? "bg-green-500/10 text-green-400"
                : "bg-red-500/10 text-red-400"
            )}
          >
            {message.text}
          </div>
        )}

        <button
          onClick={handleSave}
          disabled={isLoading || !deepgramKey || !geminiKey}
          className="rounded-lg bg-[#ff5722] px-6 py-2.5 text-[14px] font-semibold text-[#0a0a0a] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isLoading ? "Saving..." : "Save API keys"}
        </button>
      </div>
    </motion.div>
  )
}

function PlanTab({ user }: { user: { id: string; plan: string; clips_used: number } }) {
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)
  const currentPlan = PLANS[user.plan as keyof typeof PLANS]

  const handleUpgrade = async (newPlan: "byok" | "pro") => {
    setIsLoading(true)
    setMessage(null)
    try {
      const res = await fetch("/api/account/plan", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: newPlan }),
      })
      if (res.ok) {
        setMessage({ type: "success", text: `Upgraded to ${newPlan.toUpperCase()} successfully!` })
        window.location.reload()
      } else {
        const json = await res.json()
        setMessage({ type: "error", text: json.error || "Failed to upgrade." })
      }
    } catch {
      setMessage({ type: "error", text: "Something went wrong." })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <motion.div
      key="plan"
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 10 }}
      className="rounded-xl border border-white/5 bg-white/[0.02] p-6"
    >
      <h2 className="mb-6 text-[18px] font-medium text-[#f5f4ef]">Current Plan</h2>

      <div className="mb-6 rounded-lg border border-white/10 bg-white/5 p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[16px] font-medium text-[#f5f4ef]">{currentPlan?.name}</span>
              {currentPlan?.badge && (
                <span className="rounded-full bg-[#ffd700]/20 px-2 py-0.5 text-[10px] font-bold text-[#ffd700]">
                  {currentPlan.badge}
                </span>
              )}
            </div>
            <p className="mt-1 text-[13px] text-[#6a6860]">
              {currentPlan?.clips_limit === null
                ? "Unlimited clips"
                : `${currentPlan?.clips_limit} clips per month`}
            </p>
          </div>
          <div className="text-right">
            <span className="text-[16px] font-medium text-[#f5f4ef]">
              {currentPlan?.price_usd === null ? "Free" : `$${currentPlan?.price_usd}/mo`}
            </span>
          </div>
        </div>

        <div className="mt-4 border-t border-white/5 pt-4">
          <p className="text-[13px] text-[#6a6860]">
            Clips used: <span className="text-[#f5f4ef]">{user.clips_used}</span>
            {currentPlan?.clips_limit !== null && (
              <span> / {currentPlan?.clips_limit}</span>
            )}
          </p>
        </div>
      </div>

      {user.plan === "free" && (
        <div className="space-y-3">
          <p className="text-[13px] text-[#6a6860]">
            Want more clips? Upgrade to unlock unlimited generation.
          </p>
          {message && (
            <div
              className={cn(
                "rounded-lg px-4 py-3 text-[13px]",
                message.type === "success"
                  ? "bg-green-500/10 text-green-400"
                  : "bg-red-500/10 text-red-400"
              )}
            >
              {message.text}
            </div>
          )}
          <div className="flex gap-3">
            <button
              onClick={() => handleUpgrade("byok")}
              disabled={isLoading}
              className="rounded-lg border border-white/20 px-4 py-2.5 text-[14px] font-medium text-[#f5f4ef] transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Switch to BYOK
            </button>
            <button
              onClick={() => handleUpgrade("pro")}
              disabled={isLoading}
              className="rounded-lg bg-[#ff5722] px-4 py-2.5 text-[14px] font-semibold text-[#0a0a0a] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Upgrade to Pro ($19/mo)
            </button>
          </div>
        </div>
      )}

      {user.plan !== "free" && (
        <p className="text-[13px] text-[#6a6860]">
          To change your plan, please contact support.
        </p>
      )}
    </motion.div>
  )
}