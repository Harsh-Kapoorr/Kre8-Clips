import { NextRequest } from "next/server"
import { getJob } from "@/lib/job-store"
import { readFileSync, existsSync } from "fs"
import { join } from "path"

export const dynamic = "force-dynamic"

function getJobData(jobId: string) {
  const PROJECT_ROOT = join(process.cwd(), "..")
  const dataPath = join(PROJECT_ROOT, ".jobs", `${jobId}.json`)
  if (!existsSync(dataPath)) return null
  try {
    return JSON.parse(readFileSync(dataPath, "utf-8"))
  } catch {
    return null
  }
}

// Mirror of readSidecarProgress in ../route.ts. Kept local so the stream
// endpoint can deliver fresh ETA values without round-tripping through the
// JobState in-memory cache (which does not store timing fields).
interface SidecarTiming {
  step?: string
  progress?: number
  step_detail?: string
  eta_s: number | null
  elapsed_s: number | null
  eta_capped: boolean
}

function readSidecarTiming(jobId: string): SidecarTiming | null {
  const PROJECT_ROOT = join(process.cwd(), "..")
  const sidecarPath = join(PROJECT_ROOT, ".jobs", `${jobId}.progress.jsonl`)
  if (!existsSync(sidecarPath)) return null
  try {
    const content = readFileSync(sidecarPath, "utf-8")
    const lines = content.split("\n").filter(Boolean)
    if (lines.length === 0) return null
    const parsed = JSON.parse(lines[lines.length - 1]) as Record<string, unknown>
    const eta_s =
      typeof parsed.eta_s === "number" && Number.isFinite(parsed.eta_s)
        ? parsed.eta_s
        : null
    const elapsed_s =
      typeof parsed.elapsed_s === "number" && Number.isFinite(parsed.elapsed_s)
        ? parsed.elapsed_s
        : null
    return {
      step: typeof parsed.step === "string" ? parsed.step : undefined,
      progress: typeof parsed.progress === "number" ? parsed.progress : undefined,
      step_detail: typeof parsed.step_detail === "string" ? parsed.step_detail : undefined,
      eta_s,
      elapsed_s,
      eta_capped: parsed.eta_capped === true,
    }
  } catch {
    return null
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const encoder = new TextEncoder()
  let closed = false

  const stream = new ReadableStream({
    start(controller) {
      let heartbeatCount = 0

      const interval = setInterval(() => {
        if (closed) {
          clearInterval(interval)
          return
        }

        const job = getJob(id)

        if (!job) {
          if (!closed) {
            try {
              controller.enqueue(encoder.encode(`event: error\ndata: {"type": "error","data": {"error": "Job not found"}}\n\n`))
              controller.close()
            } catch {}
            closed = true
          }
          clearInterval(interval)
          return
        }

        if (job.status === "running" || job.status === "pending") {
          // Prefer sidecar values when present so the stream carries the
          // freshly computed elapsed_s / eta_s alongside step + progress.
          const timing = readSidecarTiming(id)
          const payload = {
            type: "progress",
            data: {
              step: timing?.step ?? job.step,
              progress: timing?.progress ?? job.progress,
              step_detail: timing?.step_detail ?? job.step_detail,
              eta_s: timing?.eta_s ?? null,
              elapsed_s: timing?.elapsed_s ?? null,
              eta_capped: timing?.eta_capped ?? false,
              eta_reported_at: Date.now(),
            },
          }
          try {
            controller.enqueue(encoder.encode(
              `event: progress\ndata: ${JSON.stringify(payload)}\n\n`
            ))
          } catch {}
        } else if (job.status === "done") {
          if (!closed) {
            const jobData = getJobData(id)
            const generatedClips = jobData?.generated_clips || []
            try {
              controller.enqueue(encoder.encode(`event: complete\ndata: ${JSON.stringify({ type: "complete", data: { status: "done", output_files: job.output_files, generated_clips: generatedClips } })}\n\n`))
              controller.close()
            } catch {}
            closed = true
          }
          clearInterval(interval)
          return
        } else if (job.status === "error") {
          if (!closed) {
            if (job.step === "Cancelled") {
              try {
                controller.enqueue(encoder.encode(`event: cancelled\ndata: ${JSON.stringify({ type: "cancelled", data: { status: "error", step: "Cancelled" } })}\n\n`))
                controller.close()
              } catch {}
            } else {
              try {
                controller.enqueue(encoder.encode(`event: error\ndata: ${JSON.stringify({ type: "error", data: { status: "error", error: job.error || "Unknown error" } })}\n\n`))
                controller.close()
              } catch {}
            }
            closed = true
          }
          clearInterval(interval)
          return
        }

        heartbeatCount++
        if (heartbeatCount % 30 === 0) {
          try {
            controller.enqueue(encoder.encode(`: heartbeat comment\n\n`))
          } catch {}
        }
      }, 500)
    },
    cancel() {
      closed = true
    },
  })

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  })
}
