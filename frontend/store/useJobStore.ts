"use client"

import { create } from "zustand"
import { Job, GenerationOptions } from "@/types"

const SESSION_KEY = "clipgen_job_store"
const MAX_PERSISTED_JOBS = 10
const ORPHAN_POLL_THRESHOLD = 3

let orphanPollCount = 0
let activeEventSource: EventSource | null = null

interface PersistedState {
  jobs: Job[]
  activeJobId: string | null
}

function loadFromSession(): PersistedState {
  if (typeof window === "undefined") return { jobs: [], activeJobId: null }
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (!raw) return { jobs: [], activeJobId: null }
    const parsed = JSON.parse(raw) as PersistedState
    const jobs = Array.isArray(parsed.jobs) ? parsed.jobs.slice(-MAX_PERSISTED_JOBS) : []
    return { jobs, activeJobId: parsed.activeJobId || null }
  } catch {
    return { jobs: [], activeJobId: null }
  }
}

function saveJobsToSession(jobs: Job[], activeJobId: string | null) {
  if (typeof window === "undefined") return
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ jobs: jobs.slice(-MAX_PERSISTED_JOBS), activeJobId }))
  } catch {}
}

interface JobStore {
  activeJob: Job | null
  jobs: Job[]
  isGenerating: boolean
  createJob: (url: string, options: GenerationOptions) => Promise<string>
  updateJob: (id: string, updates: Partial<Job>) => void
  setActiveJob: (job: Job | null) => void
  getJob: (id: string) => Job | undefined
  connectToProgressStream: (jobId: string) => () => void
  clearTerminalJobs: () => void
  syncFromApi: (jobs: Job[]) => void
}

export const useJobStore = create<JobStore>((set, get) => {
  const persisted = loadFromSession()
  const activeJob = persisted.activeJobId
    ? persisted.jobs.find((j) => j.id === persisted.activeJobId) ?? null
    : persisted.jobs.find((j) => j.status === "running" || j.status === "pending") ?? null
  return {
    activeJob,
    jobs: persisted.jobs,
    isGenerating: activeJob?.status === "running" || activeJob?.status === "pending",

    createJob: async (url: string, options: GenerationOptions): Promise<string> => {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, options }),
      })

      if (!response.ok) {
        const err = await response.json().catch(() => ({ error: "Failed to create job" }))
        throw new Error(err.error || "Failed to create job")
      }

      const { jobId } = await response.json()

      const job: Job = {
        id: jobId,
        url,
        status: "pending",
        progress: 0,
        step: "Starting",
        step_detail: "Initializing...",
        output_files: [],
        started_at: new Date().toISOString(),
        options,
      }

      set((state) => {
        const next = {
          jobs: [job, ...state.jobs].slice(0, MAX_PERSISTED_JOBS),
          activeJob: job,
          isGenerating: true,
        }
        saveJobsToSession(next.jobs, job.id)
        return next
      })

      get().connectToProgressStream(jobId)
      return jobId
    },

    updateJob: (id: string, updates: Partial<Job>) => {
      set((state) => {
        const jobIndex = state.jobs.findIndex((j) => j.id === id)
        if (jobIndex === -1) return state

        const updatedJobs = state.jobs.map((j) => (j.id === id ? { ...j, ...updates } : j))

        const activeJob =
          state.activeJob?.id === id ? { ...state.activeJob, ...updates } : state.activeJob

        const isGenerating = activeJob?.status === "running" || activeJob?.status === "pending"

        return { jobs: updatedJobs, activeJob, isGenerating }
      })
    },

    setActiveJob: (job: Job | null) => {
      set({
        activeJob: job,
        isGenerating: job?.status === "running" || job?.status === "pending",
      })
    },

    getJob: (id: string) => get().jobs.find((j) => j.id === id),

    connectToProgressStream: (jobId: string) => {
      if (activeEventSource) {
        activeEventSource.close()
        activeEventSource = null
      }

      let eventSource: EventSource | null = null
      let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
      let reconnectAttempts = 0
      let connected = false
      const maxReconnectAttempts = 3

      const cleanup = () => {
        connected = false
        if (reconnectTimeout) clearTimeout(reconnectTimeout)
        reconnectTimeout = null
        if (eventSource) {
          eventSource.close()
          eventSource = null
        }
        if (activeEventSource === eventSource) {
          activeEventSource = null
        }
      }

      const connect = () => {
        cleanup()
        try {
          activeEventSource = eventSource = new EventSource(`/api/jobs/${jobId}/stream`)
        } catch {
          return
        }

        connected = true

        eventSource.onopen = () => {
          reconnectAttempts = 0
        }

        eventSource.addEventListener("progress", (event: MessageEvent) => {
          reconnectAttempts = 0
          try {
            const parsed = JSON.parse(event.data)
            get().updateJob(jobId, {
              status: "running",
              progress: parsed.data.progress,
              step: parsed.data.step,
              step_detail: parsed.data.step_detail ?? "",
              // Carry timing through so PipelineProgress can show a real ETA
              // instead of extrapolating from hardcoded duration estimates.
              eta_s: parsed.data.eta_s ?? null,
              elapsed_s: parsed.data.elapsed_s ?? null,
              eta_capped: parsed.data.eta_capped ?? false,
              eta_reported_at: parsed.data.eta_reported_at ?? Date.now(),
            })
          } catch (e) {
            console.error("Failed to parse progress event:", e)
          }
        })

        eventSource.addEventListener("complete", (event: MessageEvent) => {
          try {
            const parsed = JSON.parse(event.data)
            get().updateJob(jobId, {
              status: "done",
              progress: 1,
              step: "Complete",
              step_detail: "",
              output_files: parsed.data.output_files ?? [],
              ended_at: new Date().toISOString(),
            })
            cleanup()
            fetch(`/api/jobs/${jobId}`)
              .then((r) => r.json())
              .then((enrichedJob) => {
                if (enrichedJob && enrichedJob.id) {
                  get().updateJob(jobId, enrichedJob)
                }
              })
              .catch(() => {})
          } catch (e) {
            console.error("Failed to parse complete event:", e)
          }
        })

        eventSource.addEventListener("cancelled", (event: MessageEvent) => {
          try {
            const parsed = JSON.parse(event.data)
            get().updateJob(jobId, {
              status: "error",
              step: "Cancelled",
              step_detail: "Job cancelled by user",
              ended_at: new Date().toISOString(),
            })
            cleanup()
          } catch {
          }
        })

        eventSource.addEventListener("error", (event: MessageEvent) => {
          try {
            const parsed = JSON.parse(event.data)
            const current = get().getJob(jobId)
            if (current?.step === "Cancelled") {
              cleanup()
              return
            }
            get().updateJob(jobId, {
              status: "error",
              step: "Error",
              error: parsed.data?.error || "Unknown error",
              ended_at: new Date().toISOString(),
            })
            cleanup()
          } catch {
          }
        })

        eventSource.onerror = () => {
          if (!connected) return
          connected = false
          eventSource?.close()
          eventSource = null

          const job = get().getJob(jobId)
          if (job && job.status !== "done" && job.status !== "error" && reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++
            reconnectTimeout = setTimeout(connect, Math.min(1000 * reconnectAttempts, 5000))
          } else if (!job || (job.status !== "done" && job.status !== "error")) {
            get().updateJob(jobId, {
              status: "error",
              step: "Error",
              error: reconnectAttempts >= maxReconnectAttempts ? "Connection lost to job progress stream" : "Unknown error",
              ended_at: new Date().toISOString(),
            })
          }
        }
      }

      connect()

      return cleanup
    },

    syncFromApi: (apiJobs: Job[]) => {
      set((state) => {
        let merged = [...state.jobs]
        for (const apiJob of apiJobs) {
          const idx = merged.findIndex((j) => j.id === apiJob.id)
          if (idx === -1) merged.push(apiJob)
          else {
            const existingStartedAt = new Date(merged[idx].started_at).getTime()
            const apiStartedAt = new Date(apiJob.started_at).getTime()
            const statusRank: Record<string, number> = { pending: 0, running: 1, done: 2, error: 2 }
            const existingRank = statusRank[merged[idx].status] ?? 0
            const apiRank = statusRank[apiJob.status] ?? 0
            const hasNewerData = apiStartedAt > existingStartedAt ||
              (apiStartedAt === existingStartedAt && apiRank > existingRank)
            if (hasNewerData) {
              merged[idx] = apiJob
            }
          }
        }

        let { activeJob } = state
        if (activeJob) {
          const apiVersion = merged.find((j) => j.id === activeJob!.id)
          if (apiVersion && apiVersion.started_at !== activeJob.started_at) {
            const statusRank: Record<string, number> = { pending: 0, running: 1, done: 2, error: 2 }
            const existingRank = statusRank[activeJob.status] ?? 0
            const apiRank = statusRank[apiVersion.status] ?? 0
            if (apiRank > existingRank || new Date(apiVersion.started_at) > new Date(activeJob.started_at)) {
              activeJob = apiVersion
            }
          }
        }

        const runningNow = merged.find(
          (j) => j.status === "running" || j.status === "pending"
        )

        const activeJobNotInApi = activeJob?.status === "running" &&
          !apiJobs.some((j) => j.id === activeJob!.id)

        if (activeJobNotInApi) {
          orphanPollCount++
          if (orphanPollCount >= ORPHAN_POLL_THRESHOLD) {
            const idx = merged.findIndex((j) => j.id === activeJob!.id)
            if (idx !== -1) {
              merged[idx] = { ...merged[idx], status: "error", step: "Error", step_detail: "Job disappeared from server" }
            }
            activeJob = null
            orphanPollCount = 0
            activeEventSource?.close()
            activeEventSource = null
          }
        } else {
          orphanPollCount = 0
        }

        const currentActiveIsStale =
          activeJob &&
          activeJob.status !== "done" &&
          activeJob.status !== "error" &&
          !merged.find(
            (j) =>
              j.id === activeJob?.id &&
              (j.status === "running" || j.status === "pending")
          )

        const currentActiveIsTerminal =
          activeJob &&
          (activeJob.status === "done" || activeJob.status === "error")

        if (!activeJob || currentActiveIsStale) {
          if (activeJob?.id !== runningNow?.id) {
            activeEventSource?.close()
            activeEventSource = null
          }
          if (!runningNow && merged.length > 0) {
            const doneJobs = merged.filter((j) => j.status === "done")
            const withOutput = doneJobs.filter(
              (j) => j.output_files.length > 0 || ((j as any).generated_clips?.length > 0 && (j as any).generated_clips?.[0]?.output_path)
            )
            const sortedWithOutput = withOutput.sort(
              (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
            )
            if (sortedWithOutput.length > 0) {
              activeJob = sortedWithOutput[0]
            } else {
              const sortedAll = doneJobs.sort(
                (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
              )
              activeJob = sortedAll[0] ?? null
            }
          } else {
            activeJob = runningNow ?? null
          }
        } else if (currentActiveIsTerminal && runningNow) {
          if (activeJob?.id !== runningNow.id) {
            activeEventSource?.close()
            activeEventSource = null
          }
          activeJob = runningNow
        }

        const isGenerating =
          activeJob?.status === "running" || activeJob?.status === "pending"

        saveJobsToSession(merged, activeJob?.id ?? null)
        return { jobs: merged.slice(0, MAX_PERSISTED_JOBS), activeJob, isGenerating }
      })
    },

    clearTerminalJobs: () => {
      set((state) => {
        const terminal = state.jobs.filter((j) => j.status === "done" || j.status === "error")
        const activeIsTerminal = state.activeJob?.status === "done" || state.activeJob?.status === "error"
        if (terminal.length > 0 && activeIsTerminal) {
          const next = {
            jobs: state.jobs.filter((j) => j.id !== state.activeJob?.id),
            activeJob: null,
            isGenerating: false,
          }
saveJobsToSession(next.jobs, null)
          return next
        }
        return state
      })
    },
  }
})