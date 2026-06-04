"use client"

import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { useJobStore } from "@/store/useJobStore"
import {
  Download,
  AudioWaveform,
  Mic,
  Brain,
  Scissors,
  Type,
  FolderOutput,
  Clock,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"

const STEPS = [
  { id: "downloading", label: "Downloading", icon: Download, duration_estimate: 30 },
  { id: "extracting", label: "Audio Extract", icon: AudioWaveform, duration_estimate: 15 },
  { id: "transcribing", label: "Transcribing", icon: Mic, duration_estimate: 60 },
  { id: "analyzing", label: "AI Analyze", icon: Brain, duration_estimate: 25 },
  { id: "generating", label: "Generate Clips", icon: Scissors, duration_estimate: 45 },
  { id: "captioning", label: "Burn Captions", icon: Type, duration_estimate: 30 },
  { id: "outputting", label: "Output", icon: FolderOutput, duration_estimate: 10 },
]

// Mirror of utils/progress.MAX_ETA_SECONDS. Defense in depth: the Python side
// already caps eta_s, but the legacy fallback path below extrapolates from
// hardcoded numbers, so we clamp here too.
const MAX_ETA_DISPLAY_SECONDS = 300

function getStepIndex(step: string): number {
  const map: Record<string, number> = {
    Downloading: 0,
    "Extracting Audio": 1,
    Extracting: 1,
    Transcribing: 2,
    Analyzing: 3,
    "AI Analyze": 3,
    "Generating Clips": 4,
    "Generate Clips": 4,
    Generating: 4,
    "Burning Captions": 5,
    "Burn Captions": 5,
    Captioning: 5,
    Output: 6,
    Outputting: 6,
    Complete: 6,
  }
  return map[step] ?? -1
}

function getTotalDurationEstimate(): number {
  return STEPS.reduce((sum, s) => sum + s.duration_estimate, 0)
}

function formatTime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) {
    const mins = Math.floor(seconds / 60)
    const secs = Math.round(seconds % 60)
    return `${mins}m ${secs}s`
  }
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  return `${hours}h ${mins}m`
}

export function PipelineProgress() {
  const { activeJob, updateJob } = useJobStore()
  const [startTime, setStartTime] = useState<number | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  const [isCancelling, setIsCancelling] = useState(false)

  useEffect(() => {
    if (activeJob?.status === "running" || activeJob?.status === "pending") {
      if (!startTime) {
        setStartTime(Date.now())
      }
      const interval = setInterval(() => {
        const nowMs = Date.now()
        setElapsed(Math.floor((nowMs - (startTime || nowMs)) / 1000))
        // Drive the ETA tick-down: PipelineProgress recomputes
        // displayedRemaining each render against this clock so the value
        // counts down between sidecar updates instead of freezing.
        setNow(nowMs)
      }, 1000)
      return () => clearInterval(interval)
    }
  }, [activeJob?.status, startTime])

  const handleCancel = async () => {
    if (!activeJob || isCancelling) return
    setIsCancelling(true)
    try {
      await fetch(`/api/jobs/${activeJob.id}`, { method: "DELETE" })
      updateJob(activeJob.id, {
        status: "error",
        step: "Cancelled",
        step_detail: "Job cancelled by user",
      })
    } catch (err) {
      console.error("Failed to cancel job:", err)
    } finally {
      setIsCancelling(false)
    }
  }

  if (!activeJob) return null

  const currentStepIndex = getStepIndex(activeJob.step)
  const isComplete = activeJob.status === "done"
  const isError = activeJob.status === "error"

  const totalEstimate = getTotalDurationEstimate()
  const completedDuration = STEPS.slice(0, currentStepIndex).reduce((sum, s) => sum + s.duration_estimate, 0)
  const currentStepEstimate = STEPS[currentStepIndex]?.duration_estimate || 30
  const currentStepProgress = activeJob.progress > 0 && currentStepIndex >= 0 ? activeJob.progress : 0

  // Prefer the Python-side ETA: it's computed from real elapsed time against
  // real progress, so it self-corrects when a step is slower or faster than
  // the static guesses below. Tick it down between sidecar updates against
  // the wall clock so the user sees the number move every second.
  const hasRealEta =
    typeof activeJob.eta_s === "number" &&
    activeJob.eta_s !== null &&
    typeof activeJob.eta_reported_at === "number"

  let displayedRemaining: number | null
  if (hasRealEta) {
    const sinceSampleSeconds = Math.max(0, (now - (activeJob.eta_reported_at as number)) / 1000)
    displayedRemaining = Math.max(
      0,
      Math.min(MAX_ETA_DISPLAY_SECONDS, (activeJob.eta_s as number) - sinceSampleSeconds),
    )
  } else if (currentStepIndex >= 0) {
    // Fallback: legacy static-estimate path. Used when the sidecar is missing
    // (e.g., very old jobs, or the regex-only parser path). Clamp here too so
    // the path can never go above five minutes.
    const raw = totalEstimate - completedDuration - currentStepProgress * currentStepEstimate
    displayedRemaining = Math.max(0, Math.min(MAX_ETA_DISPLAY_SECONDS, raw))
  } else {
    displayedRemaining = null
  }

  const overallProgress = isComplete
    ? 1
    : currentStepIndex >= 0
      ? (completedDuration + (currentStepProgress * currentStepEstimate)) / totalEstimate
      : 0

  return (
    <div className="flex flex-col gap-5">
      {/* Progress stats bar */}
      <div className="flex items-center justify-between rounded-lg bg-[#f5f5f5] px-4 py-2">
        <div className="flex items-center gap-2">
          <Clock className="h-3.5 w-3.5 text-[#999]" />
          <span className="text-xs text-[#666]">Elapsed</span>
          <span className="font-mono text-xs font-semibold text-[#1b1c1e]">{formatTime(elapsed)}</span>
        </div>
        {activeJob.status === "running" && displayedRemaining !== null && displayedRemaining > 0 && (
          <>
            <div className="h-3 w-px bg-[#ddd]" />
            <div className="flex items-center gap-2">
              <span className="text-xs text-[#666]">Remaining</span>
              <span
                className="font-mono text-xs font-semibold text-[#0057ff]"
                title={
                  activeJob.eta_capped
                    ? "Estimate capped — the current step is taking longer than expected"
                    : undefined
                }
              >
                {activeJob.eta_capped ? "~" : ""}{formatTime(displayedRemaining)}
              </span>
            </div>
          </>
        )}
        <div className="h-3 w-px bg-[#ddd]" />
        <div className="flex items-center gap-2">
          <span className="text-xs text-[#666]">Overall</span>
          <span className="font-mono text-xs font-semibold text-[#1b1c1e]">{Math.round(overallProgress * 100)}%</span>
        </div>
      </div>

      {/* Step nodes */}
      <div className="relative flex items-center justify-between">
        <div className="absolute inset-x-0 top-5 h-0.5 bg-[rgba(0,0,0,0.07)]" />

        <motion.div
          className="absolute inset-y-5 left-0 h-0.5 bg-gradient-to-r from-[#0057ff] to-[#ff7173]"
          initial={{ width: "0%" }}
          animate={{ width: isComplete ? "100%" : `${overallProgress * 100}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />

        {STEPS.map((step, index) => {
          const isActive = index === currentStepIndex
          const isPast = index < currentStepIndex
          const isPending = index > currentStepIndex
          const Icon = step.icon

          const stepProgress = isActive ? currentStepProgress : (isPast ? 1 : 0)

          return (
            <motion.div
              key={step.id}
              className="relative z-10 flex flex-col items-center"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: index * 0.05, duration: 0.3 }}
            >
              <div className="relative">
                <div
                  className={cn(
                    "flex h-10 w-10 items-center justify-center rounded-full border-2 transition-all duration-300",
                    isActive && "pipeline-step-active border-[#0057ff] bg-[#0057ff]/10",
                    isPast && "border-[#0057ff] bg-[#0057ff] text-white",
                    isPending && "border-[rgba(0,0,0,0.12)] bg-white text-[#999]",
                    isError && index === currentStepIndex && "border-[#f43f5e] bg-[#f43f5e]/10 text-[#f43f5e]"
                  )}
                >
                  <Icon className={cn("h-4 w-4", isPast && "text-white")} />
                </div>
                {isActive && stepProgress > 0 && (
                  <motion.div
                    className="absolute -bottom-1 left-1/2 -translate-x-1/2 h-1 w-6 rounded-full bg-[#0057ff]"
                    initial={{ width: 0 }}
                    animate={{ width: `${stepProgress * 24}px` }}
                    transition={{ duration: 0.5 }}
                  />
                )}
              </div>
              <span className={cn(
                "mt-2 text-[10px] font-medium transition-colors text-center w-16",
                isActive && "text-[#0057ff]",
                isPast && "text-[#666]",
                isPending && "text-[#ccc]"
              )}>
                {step.label}
              </span>
              <span className="text-[9px] text-[#bbb] mt-0.5">
                ~{step.duration_estimate}s
              </span>
            </motion.div>
          )
        })}
      </div>

      {/* Progress detail */}
      <div className="rounded-xl border border-[rgba(0,0,0,0.07)] bg-white p-4 shadow-[0px_5px_7px_0px_rgba(0,0,0,0.06)]">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-[#1b1c1e]">{activeJob.step}</span>
            <span className={cn(
              "rounded-full px-2 py-0.5 text-[10px] font-medium",
              isComplete && "bg-[#10b581]/10 text-[#10b581]",
              isError && "bg-[#f43f5e]/10 text-[#f43f5e]",
              activeJob.status === "running" && "bg-[#0057ff]/10 text-[#0057ff]"
            )}>
              {isComplete ? "Done" : isError ? "Failed" : activeJob.status === "running" ? "Running" : "Pending"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {activeJob.status === "running" || activeJob.status === "pending" ? (
              <button
                onClick={handleCancel}
                disabled={isCancelling}
                className="flex items-center gap-1 rounded-full bg-[#f43f5e]/10 px-3 py-1 text-xs font-medium text-[#f43f5e] transition-colors hover:bg-[#f43f5e]/20 disabled:opacity-50"
              >
                <X className="h-3 w-3" />
                {isCancelling ? "Cancelling..." : "Stop"}
              </button>
            ) : null}
            <span className="font-mono text-xs text-[#999]">
              {Math.round(overallProgress * 100)}%
            </span>
          </div>
        </div>

        <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#f5f5f5]">
          <motion.div
            className="h-full bg-gradient-to-r from-[#0057ff] to-[#ff7173]"
            initial={{ width: "0%" }}
            animate={{ width: `${overallProgress * 100}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        </div>

        <div className="mt-2 flex items-center justify-between">
          {activeJob.step_detail && (
            <p className="font-mono text-xs text-[#999] truncate max-w-[70%]" title={activeJob.step_detail}>
              {activeJob.step_detail}
            </p>
          )}
          {activeJob.status === "running" && (
            <span className="font-mono text-[10px] text-[#0057ff]">
              Step: {Math.round(currentStepProgress * 100)}%
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
