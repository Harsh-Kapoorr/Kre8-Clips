"use client"

import { useState, useEffect } from "react"
import { motion } from "framer-motion"
import { ArrowRight, Loader2 } from "lucide-react"
import { useJobStore } from "@/store/useJobStore"
import { useAuthStore } from "@/store/authStore"
import { GenerationOptions } from "@/types"
import { isLockedOut, getUpgradeMessage } from "@/lib/plans"
import { cn } from "@/lib/utils"

interface UrlInputFormProps {
  options?: Partial<GenerationOptions>
}

export function UrlInputForm({ options: passedOptions }: UrlInputFormProps) {
  const { createJob, activeJob, isGenerating } = useJobStore()
  const { user, isLoading: authLoading } = useAuthStore()
  const [url, setUrl] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    if (!user && !authLoading) {
      window.location.href = "/login?next=/#generate"
      return
    }

    if (!url.trim()) {
      setError("Paste a YouTube URL to continue.")
      return
    }
    if (!url.startsWith("https://") && !url.startsWith("http://")) {
      setError("URL must start with https://")
      return
    }

    if (user && isLockedOut(user.plan, user.clips_used)) {
      return
    }

    setIsLoading(true)
    try {
      const defaultOptions: GenerationOptions = {
        prompt: "Find engaging narrative moments with a clear hook, body, and satisfying payoff.",
        aspect_ratio: "9:16",
        min_duration: 20,
        max_duration: 65,
        num_clips: 1,
        speaker_tracking: false,
        captions: false,
        narrative: true,
        smart_narrative: false,
      }
      await createJob(url, { ...defaultOptions, ...passedOptions })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job")
    } finally {
      setIsLoading(false)
    }
  }

  const isWorking = isGenerating && activeJob?.status === "running"
  const locked = user ? isLockedOut(user.plan, user.clips_used) : false
  const notLoggedIn = !user && !authLoading

  return (
    <motion.form
      onSubmit={handleSubmit}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
      className="w-full"
    >
      <div className={cn("hero-input", error && "!border-[#ff5722]")}>
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Paste a YouTube URL — e.g. https://youtube.com/watch?v=…"
          disabled={isWorking || !!locked}
        />
        <button
          type="submit"
          disabled={isLoading || isWorking || !!locked}
        >
          {isLoading || isWorking ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Generating
            </>
          ) : locked ? (
            <>
              Unlock clips
              <ArrowRight className="h-4 w-4" />
            </>
          ) : notLoggedIn ? (
            <>
              Sign in to continue
              <ArrowRight className="h-4 w-4" />
            </>
          ) : (
            <>
              Generate clips
              <ArrowRight className="h-4 w-4" />
            </>
          )}
        </button>
      </div>
      {error && (
        <motion.p
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-2 text-[12px] text-[#ff5722]"
        >
          {error}
        </motion.p>
      )}
      {locked && user && (
        <motion.p
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-2 text-[12px] text-amber-400"
        >
          {getUpgradeMessage(user.plan, user.clips_used)}{" "}
          <a href="/pricing" className="underline hover:text-amber-300">Upgrade now →</a>
        </motion.p>
      )}
      {notLoggedIn && (
        <motion.p
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-2 text-[12px] text-[#b8b6b0]"
        >
          <a href="/login?next=/#generate" className="text-[#ff5722] underline hover:text-[#ff7040]">Sign in</a>{" "}
          or{" "}
          <a href="/signup" className="text-[#ff5722] underline hover:text-[#ff7040]">create an account</a>{" "}
          to generate clips.
        </motion.p>
      )}
    </motion.form>
  )
}