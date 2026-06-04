import { NextRequest, NextResponse } from "next/server"
import { getJob, updateJob } from "@/lib/job-store"
import { join } from "path"
import { readFileSync, writeFileSync, existsSync, unlinkSync } from "fs"
import { spawn } from "child_process"

const PROJECT_ROOT = join(process.cwd(), "..")
const JOBS_DATA_DIR = join(PROJECT_ROOT, ".jobs")

const activeProcesses = new Map<string, ReturnType<typeof spawn>>()

function getJobData(jobId: string) {
  const dataPath = join(JOBS_DATA_DIR, `${jobId}.json`)
  if (!existsSync(dataPath)) return null
  try {
    return JSON.parse(readFileSync(dataPath, "utf-8"))
  } catch {
    return null
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

function killProcessTree(pid: number, signal: NodeJS.Signals) {
  try {
    process.kill(-pid, signal)
  } catch {
    try { process.kill(pid, signal) } catch {}
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const job = getJob(id)

  if (!job) {
    return NextResponse.json({ error: "Job not found" }, { status: 404 })
  }

  const jobData = getJobData(id)
  if (jobData) {
    return NextResponse.json({
      ...job,
      video_title: jobData.video_title || job.url,
      video_duration: jobData.video_duration || 0,
      transcript: jobData.transcript || [],
      ai_analysis: jobData.ai_analysis || { segments: [], beat_timestamps: [], emotional_density: [] },
      generated_clips: jobData.generated_clips || [],
      viral_heatmap: jobData.ai_analysis?.emotional_density || [],
      broll_suggestions: jobData.broll_suggestions || [],
      clip_variations: jobData.clip_variations || {},
      clip_multi_platform_exports: jobData.clip_multi_platform_exports || {},
      status: job?.status || jobData.status || "done",
      step: job?.step || jobData.step || "Complete",
      progress: job?.progress ?? jobData.progress ?? 1,
      output_files: jobData.output_files || job?.output_files || [],
    })
  }

  return NextResponse.json({
    ...job,
    status: job?.status || "done",
    step: job?.step || "Complete",
    progress: job?.progress ?? 1,
  })
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params

  const proc = activeProcesses.get(id)
  const pid = proc?.pid ?? readPersistedPid(id)
  const stateFile = join(JOBS_DATA_DIR, `${id}.state.json`)

  updateJob(id, {
    status: "error",
    step: "Cancelled",
    progress: 0,
    step_detail: "Job cancelled by user",
    ended_at: new Date().toISOString(),
  })

  if (typeof pid === "number") {
    try { killProcessTree(pid, "SIGKILL") } catch {}
    if (!proc) {
      setTimeout(() => {
        try { killProcessTree(pid, "SIGKILL") } catch {}
      }, 100)
    }
  } else {
    activeProcesses.delete(id)
  }

  try { if (existsSync(stateFile)) unlinkSync(stateFile) } catch {}

  return NextResponse.json({ success: true, jobId: id })
}
