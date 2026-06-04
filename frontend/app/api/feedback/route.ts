import { NextRequest, NextResponse } from "next/server"
import { spawn } from "child_process"
import path from "path"
import fs from "fs"

const PROJECT_ROOT = path.resolve(process.cwd(), "..")

function trainingPath(): string {
  return path.join(PROJECT_ROOT, ".training", "clipgen_training.jsonl")
}

function feedbackPath(): string {
  return path.join(PROJECT_ROOT, ".training", "clipgen_feedback.jsonl")
}

function ensureDir(filePath: string): void {
  const dir = path.dirname(filePath)
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true })
  }
}

function readJsonl(filePath: string): any[] {
  if (!fs.existsSync(filePath)) return []
  const text = fs.readFileSync(filePath, "utf-8")
  return text
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => {
      try {
        return JSON.parse(line)
      } catch {
        return null
      }
    })
    .filter(Boolean)
}

function appendJsonl(filePath: string, record: unknown): void {
  ensureDir(filePath)
  fs.appendFileSync(filePath, JSON.stringify(record) + "\n", "utf-8")
}

function writeJsonl(filePath: string, records: any[]): void {
  ensureDir(filePath)
  const text = records.map((r) => JSON.stringify(r)).join("\n") + "\n"
  fs.writeFileSync(filePath, text, "utf-8")
}

interface FeedbackPayload {
  clip_id: string
  job_id?: string
  label: "up" | "down" | string
  source?: string
  views?: number
  shares?: number
  comments?: number
  saves?: number
  notes?: string
}

function updateTrainingOutcome(
  clipId: string,
  outcome: Record<string, unknown>
): number {
  const tp = trainingPath()
  if (!fs.existsSync(tp)) return 0
  const records = readJsonl(tp)
  let updated = 0
  for (const r of records) {
    if (r && r.clip_id === clipId && !r.outcome) {
      r.outcome = outcome
      r.outcome_recorded_at = Date.now() / 1000
      updated += 1
    }
  }
  if (updated > 0) writeJsonl(tp, records)
  return updated
}

export async function POST(req: NextRequest) {
  let body: FeedbackPayload
  try {
    body = (await req.json()) as FeedbackPayload
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 })
  }
  if (!body || !body.clip_id || !body.label) {
    return NextResponse.json(
      { error: "clip_id and label are required" },
      { status: 400 }
    )
  }

  const outcome = {
    label: body.label,
    source: body.source || "user_thumbs",
    views: body.views ?? null,
    shares: body.shares ?? null,
    comments: body.comments ?? null,
    saves: body.saves ?? null,
    notes: body.notes ?? null,
  }

  const record = {
    clip_id: body.clip_id,
    job_id: body.job_id ?? null,
    outcome,
    timestamp: Date.now() / 1000,
  }

  try {
    appendJsonl(feedbackPath(), record)
    const updated = updateTrainingOutcome(body.clip_id, outcome)
    return NextResponse.json({ ok: true, updated_training_rows: updated })
  } catch (err) {
    return NextResponse.json(
      { error: "Failed to record feedback" },
      { status: 500 }
    )
  }
}

export async function GET() {
  const fbPath = feedbackPath()
  const records = readJsonl(fbPath)
  const stats: Record<string, number> = {}
  for (const r of records) {
    const label = r.outcome?.label || "unknown"
    stats[label] = (stats[label] || 0) + 1
  }
  return NextResponse.json({
    total: records.length,
    breakdown: stats,
    storage_path: fbPath,
  })
}
