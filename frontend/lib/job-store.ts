import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync } from "fs"
import { join, dirname } from "path"
import { fileURLToPath } from "url"

export interface JobState {
  id: string
  url: string
  status: "pending" | "running" | "done" | "error"
  progress: number
  step: string
  step_detail: string
  output_files: string[]
  error?: string
  started_at: string
  ended_at?: string
  options: Record<string, unknown>
}

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = join(FRONTEND_DIR, "..")
const JOBS_DIR = join(PROJECT_ROOT, ".jobs")

function ensureJobsDir() {
  if (!existsSync(JOBS_DIR)) {
    mkdirSync(JOBS_DIR, { recursive: true })
  }
}

function jobFilePath(id: string): string {
  return join(JOBS_DIR, `${id}.json`)
}

export function getJob(id: string): JobState | undefined {
  const filePath = jobFilePath(id)
  if (!existsSync(filePath)) {
    try {
      const allJobs = readdirSync(JOBS_DIR).filter((f) => f.endsWith(".json"))
      for (const f of allJobs) {
        const d = JSON.parse(readFileSync(join(JOBS_DIR, f), "utf-8")) as Record<string, unknown>
        if (d.job_id === id || d.id === id) {
          const job = d as unknown as JobState
          if (!job.id && d.job_id) job.id = d.job_id as string
          return job
        }
      }
    } catch {}
    return undefined
  }
  try {
    const d = JSON.parse(readFileSync(filePath, "utf-8")) as Record<string, unknown>
    const job = d as unknown as JobState
    if (!job.id && d.job_id) job.id = d.job_id as string
    return job
  } catch {
    return undefined
  }
}

export function setJob(id: string, job: JobState): void {
  ensureJobsDir()
  const filePath = jobFilePath(id)
  const existing = getJobDataSync(id)
  if (existing) {
    const merged = { ...existing, ...job }
    writeFileSync(filePath, JSON.stringify(merged, null, 2), "utf-8")
  } else {
    writeFileSync(filePath, JSON.stringify(job), "utf-8")
  }
}

function getJobDataSync(id: string): Record<string, unknown> | null {
  const filePath = jobFilePath(id)
  if (!existsSync(filePath)) return null
  try {
    return JSON.parse(readFileSync(filePath, "utf-8")) as Record<string, unknown>
  } catch {
    return null
  }
}

export function updateJob(id: string, updates: Partial<JobState>): void {
  const job = getJob(id)
  if (!job) return
  const updated = { ...job, ...updates }
  setJob(id, updated)
}

export function getAllJobs(): JobState[] {
  ensureJobsDir()
  try {
    return readdirSync(JOBS_DIR)
      .filter((f) => f.endsWith(".json"))
      .map((f) => {
        try {
          const d = JSON.parse(readFileSync(join(JOBS_DIR, f), "utf-8")) as Record<string, unknown>
          const job = d as unknown as JobState
          if (!job.id && d.job_id) job.id = d.job_id as string
          return job
        } catch {
          return null
        }
      })
      .filter((j): j is JobState => j !== null && Boolean(j.id) && Boolean(j.status))
  } catch {
    return []
  }
}