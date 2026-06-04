import { NextRequest, NextResponse } from "next/server"
import { spawn } from "child_process"
import { randomUUID } from "crypto"
import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync, statSync, unlinkSync } from "fs"
import { join, dirname } from "path"
import { fileURLToPath } from "url"
import { getJob, setJob, updateJob, getAllJobs, JobState } from "@/lib/job-store"
import { findUserById, incrementClipsUsed } from "@/backend/auth/db"
import { isLockedOut } from "@/lib/plans"

const __dirname = dirname(fileURLToPath(import.meta.url))
const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = join(FRONTEND_DIR, "..")
const JOBS_DATA_DIR = join(PROJECT_ROOT, ".jobs")

const activeProcesses = new Map<string, ReturnType<typeof spawn>>()

interface AiAnalysis {
  segments: unknown[]
  beat_timestamps: unknown[]
  emotional_density: unknown[]
}

interface JobData {
  video_title?: string
  video_duration?: number
  transcript?: unknown[]
  ai_analysis?: AiAnalysis
  generated_clips?: unknown[]
  creator_profile?: null
  broll_suggestions?: unknown[]
  clip_variations?: Record<string, unknown>
  clip_multi_platform_exports?: Record<string, unknown>
}

function getJobData(jobId: string): JobData | null {
  const dataPath = join(JOBS_DATA_DIR, `${jobId}.json`)
  if (!existsSync(dataPath)) return null
  try {
    return JSON.parse(readFileSync(dataPath, "utf-8")) as JobData
  } catch {
    return null
  }
}

function getPythonJobs(): Array<Record<string, unknown>> {
  try {
    if (!existsSync(JOBS_DATA_DIR)) return []
    const storeIds = new Set(getAllJobs().map((j: JobState) => j.id).filter(Boolean))
    return readdirSync(JOBS_DATA_DIR)
      .filter((f) => f.endsWith(".json"))
      .map((f) => {
        try {
          const data = JSON.parse(readFileSync(join(JOBS_DATA_DIR, f), "utf-8"))
          const hasPythonSchema = Boolean(data.job_id && data.generated_clips?.length > 0)
          const hasStoreSchema = Boolean(data.id && data.status)
          if (hasPythonSchema && !hasStoreSchema && !storeIds.has(data.job_id)) {
            return {
              id: data.job_id,
              url: data.url || "",
              status: "done",
              progress: 1,
              step: "Complete",
              step_detail: "",
              output_files: data.generated_clips.map((c: Record<string, unknown>) => c.output_path || "").filter(Boolean),
              started_at: data.created_at || new Date().toISOString(),
              ended_at: data.completed_at || new Date().toISOString(),
              options: {},
              ...data,
            }
          }
          return null
        } catch {
          return null
        }
      })
      .filter((j): j is Record<string, unknown> => j !== null)
  } catch {
    return []
  }
}

function enrichJobWithAnalysis(jobId: string, url: string): Record<string, unknown> {
  const jobData = getJobData(jobId)
  const job = getJob(jobId)
  if (!job) return {}

  const base: Record<string, unknown> = {
    id: job.id,
    url: job.url,
    status: job.status,
    progress: job.progress,
    step: job.step,
    step_detail: job.step_detail,
    output_files: job.output_files,
    error: job.error,
    started_at: job.started_at,
    ended_at: job.ended_at,
    options: job.options,
  }

  const sidecar = readSidecarProgress(jobId)
  if (sidecar) {
    base.step = sidecar.step
    base.progress = sidecar.progress
    base.step_detail = sidecar.step_detail
    base.eta_s = sidecar.eta_s
    base.elapsed_s = sidecar.elapsed_s
    base.eta_capped = sidecar.eta_capped
    base.eta_reported_at = sidecar.eta_reported_at
  }

  if (jobData) {
    const generatedClips = (jobData.generated_clips || []) as Array<{output_path?: string}>
    const outputFiles = generatedClips
      .map((c) => c.output_path)
      .filter((p): p is string => Boolean(p))
    return {
      ...base,
      video_title: jobData.video_title || extractVideoTitle(url),
      video_duration: jobData.video_duration || 0,
      transcript: jobData.transcript || [],
      ai_analysis: jobData.ai_analysis || { segments: [], beat_timestamps: [], emotional_density: [] },
      generated_clips: generatedClips,
      output_files: outputFiles.length > 0 ? outputFiles : job.output_files,
      creator_profile: jobData.creator_profile || null,
      viral_heatmap: jobData.ai_analysis?.emotional_density || [],
      broll_suggestions: jobData.broll_suggestions || [],
      clip_variations: jobData.clip_variations || {},
      clip_multi_platform_exports: jobData.clip_multi_platform_exports || {},
    }
  }

  return {
    ...base,
    video_title: extractVideoTitle(url),
  }
}

function extractVideoTitle(url: string): string {
  try {
    const u = new URL(url)
    return u.searchParams.get("v") || u.pathname.split("/").pop() || "Video"
  } catch {
    return "Video"
  }
}

const STEP_PATTERNS = [
  { pattern: /\[1\/7\]\s*→?\s*(.+)/i, step: "Validating", index: 0 },
  { pattern: /\[2\/7\]\s*→?\s*(.+)/i, step: "Downloading", index: 1 },
  { pattern: /\[3\/7\]\s*→?\s*(.+)/i, step: "Extracting Audio", index: 2 },
  { pattern: /\[4\/7\]\s*→?\s*(.+)/i, step: "Transcribing", index: 3 },
  { pattern: /\[5\/7\]\s*→?\s*(.+)/i, step: "Analyzing", index: 4 },
  { pattern: /\[6\/7\]\s*→?\s*(.+)/i, step: "Generating Clips", index: 5 },
  { pattern: /\[7\/7\]\s*→?\s*(.+)/i, step: "Complete", index: 6 },
  { pattern: /Downloading video/i, step: "Downloading", index: 1 },
  { pattern: /Downloading/i, step: "Downloading", index: 1 },
  { pattern: /Extracting audio/i, step: "Extracting Audio", index: 2 },
  { pattern: /Transcribing/i, step: "Transcribing", index: 3 },
  { pattern: /Analyzing transcript/i, step: "Analyzing", index: 4 },
  { pattern: /Analyzing for narrative/i, step: "Analyzing", index: 4 },
  { pattern: /Analyzing/i, step: "Analyzing", index: 4 },
  { pattern: /Generating clip/i, step: "Generating Clips", index: 5 },
  { pattern: /Generating clips/i, step: "Generating Clips", index: 5 },
  { pattern: /Burning captions/i, step: "Burning Captions", index: 5 },
  { pattern: /Complete/i, step: "Complete", index: 6 },
  { pattern: /No clips identified/i, step: "Analyzing", index: 4 },
  { pattern: /! (.+)/i, step: "Analyzing", index: 4 },
] as Array<{ pattern: RegExp; step: string; index?: number }>

function parseProgress(line: string): { step: string; progress: number; step_detail: string } | null {
  for (const sp of STEP_PATTERNS) {
    const match = line.match(sp.pattern)
    if (match) {
      const step = sp.step
      const progress = typeof sp.index === "number" ? (sp.index + 0.5) / 7 : 0.5
      let step_detail = match[1]?.trim() || ""
      if (step_detail.startsWith("→")) step_detail = step_detail.substring(1).trim()
      return { step, progress, step_detail }
    }
  }
  const pctMatch = line.match(/(\d+)%/)
  if (pctMatch) {
    return {
      step: "Processing",
      progress: parseInt(pctMatch[1]) / 100,
      step_detail: line.substring(0, 100),
    }
  }
  return null
}

function readSidecarProgress(jobId: string): {
  step: string
  progress: number
  step_detail: string
  eta_s: number | null
  elapsed_s: number | null
  eta_capped: boolean
  eta_reported_at: number
} | null {
  const sidecarPath = join(JOBS_DATA_DIR, `${jobId}.progress.jsonl`)
  if (!existsSync(sidecarPath)) return null
  try {
    const content = readFileSync(sidecarPath, "utf-8")
    const lines = content.split("\n").filter(Boolean)
    if (lines.length === 0) return null
    const parsed = JSON.parse(lines[lines.length - 1]) as Record<string, unknown>
    if (typeof parsed.step !== "string" || typeof parsed.progress !== "number") return null
    // The Python side writes elapsed_s / eta_s on every event. Older sidecar
    // files (pre-timing patch) won't have them — fall back to nulls so the UI
    // can detect that and skip the remaining-time display rather than show a
    // bogus number.
    const eta_s =
      typeof parsed.eta_s === "number" && Number.isFinite(parsed.eta_s)
        ? parsed.eta_s
        : null
    const elapsed_s =
      typeof parsed.elapsed_s === "number" && Number.isFinite(parsed.elapsed_s)
        ? parsed.elapsed_s
        : null
    return {
      step: parsed.step,
      progress: parsed.progress,
      step_detail: typeof parsed.step_detail === "string" ? parsed.step_detail : "",
      eta_s,
      elapsed_s,
      eta_capped: parsed.eta_capped === true,
      // The wall-clock moment we read this event. The UI uses this to tick
      // the displayed ETA down between sidecar updates so a slow step doesn't
      // freeze the number.
      eta_reported_at: Date.now(),
    }
  } catch {
    return null
  }
}

function sanitizeFilename(url: string): string {
  try {
    const u = new URL(url)
    const videoId = u.searchParams.get("v") || u.pathname.split("/").pop()
    return videoId || url.replace(/[^a-zA-Z0-9]/g, "_").slice(0, 30)
  } catch {
    return url.replace(/[^a-zA-Z0-9]/g, "_").slice(0, 30)
  }
}

function findGeneratedClips(jobId: string, jobUrl: string): string[] {
  try {
    const jobDir = join(PROJECT_ROOT, ".jobs", jobId)
    const outputDir = join(PROJECT_ROOT, "output")

    const checkDir = (dir: string) => {
      if (!existsSync(dir)) return []
      const { readdirSync, statSync } = require("fs")
      return readdirSync(dir)
        .filter((f: string) => f.endsWith(".mp4") || f.endsWith(".mov") || f.endsWith(".webm"))
        .map((f: string) => ({
          name: f,
          mtime: statSync(join(dir, f)).mtime.getTime(),
          dir,
        }))
    }

    const jobFiles = checkDir(jobDir)
    const outputFiles = checkDir(outputDir)

    const sanitizeUrlForMatch = (url: string): string => {
      try {
        const u = new URL(url)
        return u.searchParams.get("v") || u.pathname.split("/").pop() || ""
      } catch {
        return ""
      }
    }

    const videoId = sanitizeUrlForMatch(jobUrl)

    const candidates = [...jobFiles, ...outputFiles]
      .filter((f, i, arr) => arr.findIndex(x => x.name === f.name) === i)
      .sort((a: { mtime: number }, b: { mtime: number }) => b.mtime - a.mtime)

    let jobDirClips = candidates.filter((f: { name: string; dir: string }) =>
      f.dir === jobDir && f.name.includes("clip_")
    )

    if (jobDirClips.length > 0) {
      return jobDirClips.slice(0, 10).map((f: { name: string; dir: string }) => {
        return `/.jobs/${jobId}/${f.name}`
      })
    }

    const filtered = candidates.filter((f: { name: string }) => {
      if (f.name.includes(videoId)) return true
      if (f.name.includes("clip_") && f.name.includes(videoId)) return true
      return false
    })

    const results = filtered.slice(0, 10).map((f: { name: string; dir: string }) => {
      if (f.dir === jobDir) {
        return `/.jobs/${jobId}/${f.name}`
      }
      return `/output/${f.name}`
    })

    return results
  } catch {
    return []
  }
}

function loadEnv(): Record<string, string> {
  try {
    const envPath = join(PROJECT_ROOT, ".env")
    const content = readFileSync(envPath, "utf-8")
    const env: Record<string, string> = {}
    for (const line of content.split("\n")) {
      const trimmed = line.trim()
      if (trimmed && !trimmed.startsWith("#")) {
        const [key, ...vals] = trimmed.split("=")
        if (key) env[key.trim()] = vals.join("=").trim()
      }
    }
    return env
  } catch {
    return {}
  }
}

function getPythonPath(): string {
  const candidates = [
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13",
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
    "/opt/homebrew/bin/python3.11",
    "/usr/local/bin/python3",
    "/usr/bin/python3",
    "python3",
  ]
  for (const p of candidates) {
    if (existsSync(p)) return p
  }
  return "python3"
}

export async function POST(request: NextRequest) {
  const userId = request.headers.get("x-user-id")
  if (!userId) {
    return NextResponse.json({ error: "Authentication required" }, { status: 401 })
  }

  const user = findUserById(userId)
  if (!user) {
    return NextResponse.json({ error: "User not found" }, { status: 404 })
  }

  const plan = user.plan as "free" | "byok" | "pro"
  const clipsUsed = user.clips_used ?? 0

  if (isLockedOut(plan, clipsUsed)) {
    const upgradeUrl = "/pricing"
    return NextResponse.json(
      {
        error: "You've reached your clip limit.",
        upgrade_url: upgradeUrl,
        message: plan === "free"
          ? "You've used your free clip. Upgrade to Pro or BYOK to continue."
          : "You've reached your clip limit for this month.",
      },
      { status: 402 }
    )
  }

  if (plan === "byok" && (!user.deepgram_key || !user.gemini_key)) {
    return NextResponse.json(
      {
        error: "API keys required",
        upgrade_url: "/account?tab=apikeys",
        message: "Please add your Deepgram and Gemini API keys in your account settings to use the BYOK plan.",
      },
      { status: 402 }
    )
  }

  const { url, options = {} } = await request.json()

  if (!url || typeof url !== "string") {
    return NextResponse.json({ error: "URL is required" }, { status: 400 })
  }

  const jobId = randomUUID().slice(0, 8)
  const pythonPath = getPythonPath()
  const clipgenPath = join(PROJECT_ROOT, "clipgen.py")

  if (!existsSync(clipgenPath)) {
    return NextResponse.json({ error: `clipgen.py not found at ${clipgenPath}` }, { status: 500 })
  }

  const jobDir = join(PROJECT_ROOT, ".jobs", jobId)
  mkdirSync(jobDir, { recursive: true })

  const args = [
    clipgenPath,
    url,
    "--aspect-ratio", options.aspect_ratio || "9:16",
    "--min-duration", String(options.min_duration || 20),
    "--max-duration", String(options.max_duration || 65),
    "--num-clips", String(options.num_clips || 5),
    "--job-dir", jobDir,
  ]

  if (options.prompt && String(options.prompt).trim()) {
    args.push("--prompt", String(options.prompt).trim())
  } else {
    args.push("--prompt", "Find the most engaging, complete narrative moments. Look for stories with a beginning, middle, and end. Find lessons, insights, or powerful stories that can stand alone.")
  }
  if (options.speaker_tracking) args.push("--speaker-tracking")
  if (options.captions) {
    args.push("--captions")
    if (options.caption_style) args.push("--caption-style", options.caption_style)
  }
  if (options.narrative) args.push("--narrative")
  if (options.smart_narrative) args.push("--smart-narrative")

  const env = loadEnv()
  const startedAt = new Date().toISOString()

  let proc: ReturnType<typeof spawn>
  try {
    proc = spawn(pythonPath, args, {
      cwd: PROJECT_ROOT,
      env: { ...process.env, ...env },
      detached: true,
    })
  } catch (err: any) {
    console.error("Failed to spawn process:", err)
    return NextResponse.json({ error: `Failed to start Python: ${err.message}` }, { status: 500 })
  }

  const jobStateFile = join(JOBS_DATA_DIR, `${jobId}.state.json`)
  try {
    writeFileSync(jobStateFile, JSON.stringify({ pid: proc.pid, started_at: startedAt }), "utf-8")
  } catch {}

  const job = {
    id: jobId,
    url,
    status: "running" as const,
    progress: 0,
    step: "Starting",
    step_detail: "Initializing...",
    output_files: [] as string[],
    started_at: startedAt,
    options,
  }

  setJob(jobId, job)
  activeProcesses.set(jobId, proc)

  proc.stdout?.on("data", (data: Buffer) => {
    if (getJob(jobId)?.step === "Cancelled") return
    const lines = data.toString().split("\n").filter(Boolean)
    for (const line of lines) {
      const parsed = parseProgress(line)
      if (parsed) {
        updateJob(jobId, {
          step: parsed.step,
          progress: parsed.progress,
          step_detail: parsed.step_detail.substring(0, 200),
        })
      }
    }
  })

  proc.stderr?.on("data", (data: Buffer) => {
    const text = data.toString()
    console.error("clipgen stderr:", text)
    if (getJob(jobId)?.step === "Cancelled") return
    const parsed = parseProgress(text)
    if (parsed) {
      updateJob(jobId, {
        step: parsed.step,
        progress: parsed.progress,
        step_detail: parsed.step_detail.substring(0, 200),
      })
    } else {
      const warningMatch = text.match(/! (.+)/)
      if (warningMatch) {
        updateJob(jobId, {
          step: "Analyzing",
          progress: 0.7,
          step_detail: warningMatch[1].substring(0, 200),
        })
      }
    }
  })

  proc.on("error", (err: Error) => {
    console.error("Python process error:", err)
    updateJob(jobId, {
      status: "error",
      step: "Error",
      error: `Failed to start: ${err.message}`,
      ended_at: new Date().toISOString(),
    })
  })

  proc.on("close", (code: number | null) => {
    activeProcesses.delete(jobId)
    try { if (existsSync(jobStateFile)) unlinkSync(jobStateFile) } catch {}
    if (getJob(jobId)?.step === "Cancelled") return
    if (code === 0) {
      incrementClipsUsed(userId)
      updateJob(jobId, {
        status: "done",
        progress: 1,
        step: "Complete",
        step_detail: "",
        output_files: findGeneratedClips(jobId, url),
        ended_at: new Date().toISOString(),
      })
    } else if (code === 1) {
      updateJob(jobId, {
        status: "done",
        progress: 1,
        step: "Complete",
        step_detail: "No clips found matching criteria. Try a different prompt or video.",
        output_files: findGeneratedClips(jobId, url),
        ended_at: new Date().toISOString(),
      })
    } else {
      updateJob(jobId, {
        status: "error",
        step: "Error",
        error: `Process exited with code ${code}`,
        ended_at: new Date().toISOString(),
      })
    }
  })

  return NextResponse.json({ jobId, createdAt: startedAt })
}

function killProcessTree(pid: number, signal: NodeJS.Signals = "SIGTERM") {
  try {
    process.kill(-pid, signal)
  } catch {
    try { process.kill(pid, signal) } catch {}
  }
}

function readPersistedPid(jobId: string): number | null {
  const stateFile = join(JOBS_DATA_DIR, `${jobId}.state.json`)
  if (!existsSync(stateFile)) return null
  try {
    const data = JSON.parse(readFileSync(stateFile, "utf-8")) as { pid?: number }
    return typeof data.pid === "number" ? data.pid : null
  } catch {
    return null
  }
}

export async function DELETE(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const jobId = searchParams.get("id")

  if (!jobId) {
    return NextResponse.json({ error: "jobId is required" }, { status: 400 })
  }

  const proc = activeProcesses.get(jobId)
  const pid = proc?.pid ?? readPersistedPid(jobId)
  const stateFile = join(JOBS_DATA_DIR, `${jobId}.state.json`)

  if (typeof pid === "number") {
    try { writeFileSync("/tmp/clipgen-cancel.log", `Cancelling ${jobId} PID=${pid} at ${new Date().toISOString()}\n`, { flag: "a" }); } catch {}
    console.error(`[cancel] Cancelling job ${jobId} with PID ${pid}`)
    try {
      process.kill(-pid, "SIGKILL")
      try { writeFileSync("/tmp/clipgen-cancel.log", `SIGKILL sent to -${pid}\n`, { flag: "a" }); } catch {}
      console.error(`[cancel] SIGKILL sent to -${pid}`)
    } catch (e: any) {
      try { writeFileSync("/tmp/clipgen-cancel.log", `SIGKILL to -${pid} failed: ${e.message}\n`, { flag: "a" }); } catch {}
      console.error(`[cancel] SIGKILL to -${pid} failed: ${e.message}, trying +${pid}`)
      try {
        process.kill(pid, "SIGKILL")
        try { writeFileSync("/tmp/clipgen-cancel.log", `SIGKILL sent to +${pid}\n`, { flag: "a" }); } catch {}
        console.error(`[cancel] SIGKILL sent to +${pid}`)
      } catch (e2: any) {
        try { writeFileSync("/tmp/clipgen-cancel.log", `SIGKILL to +${pid} failed: ${e2.message}\n`, { flag: "a" }); } catch {}
        console.error(`[cancel] SIGKILL to +${pid} failed: ${e2.message}`)
      }
    }
    if (!proc) {
      setTimeout(() => {
        try { killProcessTree(pid, "SIGKILL") } catch {}
      }, 100)
    }
  } else {
    try { writeFileSync("/tmp/clipgen-cancel.log", `No PID for job ${jobId}\n`, { flag: "a" }); } catch {}
    console.error(`[cancel] No PID for job ${jobId}, cannot kill`)
    activeProcesses.delete(jobId)
  }

  try { if (existsSync(stateFile)) unlinkSync(stateFile) } catch {}

  updateJob(jobId, {
    status: "error",
    step: "Cancelled",
    progress: 0,
    step_detail: "Job cancelled by user",
    ended_at: new Date().toISOString(),
  })

  return NextResponse.json({ success: true, jobId })
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const jobId = searchParams.get("id")
  const action = searchParams.get("action")

  if (jobId && action === "analysis") {
    const job = getJob(jobId)
    if (!job) return NextResponse.json({ error: "job not found" }, { status: 404 })
    const data = getJobData(jobId)
    if (!data) return NextResponse.json({ error: "analysis not available yet" }, { status: 404 })
    return NextResponse.json({
      ai_analysis: data.ai_analysis || { segments: [], beat_timestamps: [], emotional_density: [] },
      transcript: data.transcript || [],
      viral_heatmap: data.ai_analysis?.emotional_density || [],
      broll_suggestions: data.broll_suggestions || [],
    })
  }

  if (jobId) {
    const job = getJob(jobId)
    if (!job) return NextResponse.json({ error: "job not found" }, { status: 404 })
    return NextResponse.json(enrichJobWithAnalysis(jobId, job.url))
  }

  const jobs = getAllJobs()
  const pythonJobs = getPythonJobs()
  return NextResponse.json([...jobs, ...pythonJobs])
}
