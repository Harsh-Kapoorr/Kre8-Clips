"use client"

import { useEffect, useRef, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useJobStore } from "@/store/useJobStore"
import { GeneratedClip } from "@/types"
import { Activity, Film, Loader2, Clock, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"

const POLL_INTERVAL_MS = 2000
const LOG_MAX_ENTRIES = 50

interface LogEntry {
  id: number
  text: string
  timestamp: number
}

export function LivePreview() {
  const { activeJob } = useJobStore()
  const [log, setLog] = useState<LogEntry[]>([])
  const [clipsSoFar, setClipsSoFar] = useState<GeneratedClip[]>([])
  const [now, setNow] = useState(() => Date.now())
  const logIdRef = useRef(0)
  const lastStepDetailRef = useRef<string>("")
  const lastClipCountRef = useRef(0)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (activeJob?.status === "running" || activeJob?.status === "pending") {
      const interval = setInterval(() => setNow(Date.now()), 1000)
      return () => clearInterval(interval)
    }
  }, [activeJob?.status])

  useEffect(() => {
    if (!activeJob || (activeJob.status !== "running" && activeJob.status !== "pending")) {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
      return
    }

    const startPolling = async () => {
      pollIntervalRef.current = setInterval(async () => {
        if (!activeJob) return
        try {
          const res = await fetch(`/api/jobs/${activeJob.id}`)
          if (!res.ok) return
          const job = await res.json()
          const clips: GeneratedClip[] = job.generated_clips ?? []
          if (clips.length > lastClipCountRef.current) {
            lastClipCountRef.current = clips.length
            setClipsSoFar(clips)
          }
        } catch {}
      }, POLL_INTERVAL_MS)
    }

    startPolling()
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
    }
  }, [activeJob?.id, activeJob?.status])

  useEffect(() => {
    const detail = activeJob?.step_detail ?? ""
    if (detail && detail !== lastStepDetailRef.current) {
      lastStepDetailRef.current = detail
      setLog((prev) => {
        const entry: LogEntry = { id: logIdRef.current++, text: detail, timestamp: Date.now() }
        return [entry, ...prev].slice(0, LOG_MAX_ENTRIES)
      })
    }
  }, [activeJob?.step_detail])

  if (!activeJob || (activeJob.status !== "running" && activeJob.status !== "pending")) {
    return null
  }

  const elapsed = activeJob.elapsed_s ?? 0
  const eta = activeJob.eta_s
  const etaCapped = activeJob.eta_capped ?? false

  function formatTime(seconds: number): string {
    if (seconds < 60) return `${Math.round(seconds)}s`
    const mins = Math.floor(seconds / 60)
    const secs = Math.round(seconds % 60)
    return `${mins}m ${secs}s`
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 12 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="mx-auto max-w-3xl"
    >
      <div className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0f0f0f] overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.4)]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.06)] px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-[#ff5722]/10">
              <Activity className="h-3.5 w-3.5 text-[#ff5722]" />
            </div>
            <span className="text-[13px] font-semibold text-[#f5f4ef]">Live Preview</span>
            <div className="flex h-1.5 w-1.5 items-center justify-center">
              <div className="absolute h-1.5 w-1.5 animate-ping rounded-full bg-[#ff5722] opacity-75" />
              <div className="h-1.5 w-1.5 rounded-full bg-[#ff5722]" />
            </div>
          </div>

          <div className="flex items-center gap-3">
            {elapsed > 0 && (
              <div className="flex items-center gap-1.5">
                <Clock className="h-3 w-3 text-[#666]" />
                <span className="font-mono text-[11px] text-[#999]">
                  {formatTime(elapsed)}
                </span>
              </div>
            )}
            {eta !== null && eta !== undefined && eta > 0 && (
              <>
                <div className="h-3 w-px bg-[rgba(255,255,255,0.08)]" />
                <div className="flex items-center gap-1.5" title={etaCapped ? "Estimate capped — step is taking longer than expected" : undefined}>
                  <span className="font-mono text-[11px] text-[#666]">ETA</span>
                  <span className={cn("font-mono text-[11px] font-semibold", etaCapped ? "text-[#ffb547]" : "text-[#999]")}>
                    {etaCapped ? "~" : ""}{formatTime(eta)}
                  </span>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Source video banner */}
        <div className="flex items-center gap-3 border-b border-[rgba(255,255,255,0.04)] px-5 py-2.5">
          <Film className="h-3.5 w-3.5 text-[#555]" />
          <span className="truncate text-[12px] text-[#888]" title={activeJob.url}>
            {activeJob.video_title ?? activeJob.url}
          </span>
        </div>

        {/* Activity log */}
        <div className="px-5 py-3">
          <div className="mb-2 flex items-center gap-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-[#555]">Activity Log</span>
            <div className="h-px flex-1 bg-[rgba(255,255,255,0.05)]" />
          </div>

          <div
            className="space-y-1.5"
            role="log"
            aria-label="Job activity log"
            aria-live="polite"
          >
            <AnimatePresence initial={false}>
              {log.length === 0 && (
                <motion.p
                  key="empty"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="py-2 text-[12px] text-[#555]"
                >
                  Waiting for activity...
                </motion.p>
              )}
              {log.map((entry) => (
                <motion.div
                  key={entry.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="flex items-start gap-2"
                >
                  <span className="mt-0.5 h-1 w-1 rounded-full bg-[#ff5722] opacity-60 shrink-0" />
                  <span className="font-mono text-[11.5px] text-[#777] leading-5">
                    {entry.text}
                  </span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>

        {/* Clips rendered so far */}
        {clipsSoFar.length > 0 && (
          <div className="border-t border-[rgba(255,255,255,0.04)] px-5 py-3">
            <div className="mb-2.5 flex items-center gap-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-[#555]">
                Clips Generated
              </span>
              <span className="rounded-full bg-[#ff5722]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#ff5722]">
                {clipsSoFar.length}
              </span>
              <div className="h-px flex-1 bg-[rgba(255,255,255,0.05)]" />
            </div>

            <div className="space-y-2">
              {clipsSoFar.map((clip, i) => (
                <div
                  key={clip.id ?? i}
                  className="flex items-center justify-between rounded-lg border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] px-3.5 py-2.5"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12px] font-medium text-[#ccc]" title={clip.title}>
                      {clip.title}
                    </p>
                    <div className="mt-0.5 flex items-center gap-2">
                      <span className="font-mono text-[10px] text-[#555]">
                        {clip.duration_seconds}s
                      </span>
                      {clip.hook_score && (
                        <span className="font-mono text-[10px] text-[#555]">
                          score {clip.hook_score.toFixed(1)}
                        </span>
                      )}
                    </div>
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 text-[#444] shrink-0 ml-2" />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Polling indicator */}
        {activeJob.status === "running" && (
          <div className="flex items-center gap-2 border-t border-[rgba(255,255,255,0.04)] px-5 py-2">
            <Loader2 className="h-3 w-3 animate-spin text-[#444]" />
            <span className="text-[10px] text-[#444]">
              Checking for new clips...
            </span>
          </div>
        )}
      </div>
    </motion.div>
  )
}