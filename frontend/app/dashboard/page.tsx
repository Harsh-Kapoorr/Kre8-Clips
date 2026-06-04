"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { useAuthStore } from "@/store/authStore"
import { useJobStore } from "@/store/useJobStore"
import { authFetch } from "@/lib/authFetch"
import { Job } from "@/types"
import {
  ArrowRight,
  Sparkles,
  Video,
  CheckCircle2,
  XCircle,
  Loader2,
  Calendar,
  Film,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { ClipCard } from "@/components/clip-card"

type FilterTab = "all" | "running" | "done" | "error"

const STATUS_CONFIG = {
  running: { label: "In Progress", icon: Loader2, color: "text-[#0057ff] bg-[#0057ff]/10" },
  done: { label: "Done", icon: CheckCircle2, color: "text-[#10b581] bg-[#10b581]/10" },
  error: { label: "Error", icon: XCircle, color: "text-[#f43f5e] bg-[#f43f5e]/10" },
  pending: { label: "Pending", icon: Loader2, color: "text-[#f59e0b] bg-[#f59e0b]/10" },
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

function formatRelativeDate(dateStr: string) {
  const now = Date.now()
  const diff = now - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  if (hours < 24) return `${hours}h ago`
  if (days < 7) return `${days}d ago`
  return formatDate(dateStr)
}

interface JobCardProps {
  job: Job
  isActive: boolean
  onSelect: (job: Job) => void
}

function JobCard({ job, isActive, onSelect }: JobCardProps) {
  const config = STATUS_CONFIG[job.status] ?? STATUS_CONFIG.pending
  const Icon = config.icon
  const clipCount = job.output_files.length || (job as any).generated_clips?.length || 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "rounded-xl border border-white/[0.06] bg-[#0e0e0e] p-5 transition-all cursor-pointer hover:border-white/[0.12] hover:bg-[#111]",
        isActive && "ring-1 ring-[#ff5722]/30"
      )}
      onClick={() => onSelect(job)}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1.5">
            <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold", config.color)}>
              <Icon className="h-3 w-3" />
              {config.label}
            </span>
            {clipCount > 0 && (
              <span className="text-[11px] text-[#8a8880]">
                {clipCount} clip{clipCount !== 1 ? "s" : ""}
              </span>
            )}
          </div>
          <p className="text-[14px] font-medium text-[#f5f4ef] truncate mb-1">
            {job.url}
          </p>
          <div className="flex items-center gap-3 text-[11px] text-[#6a6860]">
            <span className="flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {formatRelativeDate(job.started_at)}
            </span>
            {job.step && job.status === "running" && (
              <span>{job.step}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 text-[#6a6860]">
          <Film className="h-4 w-4" />
        </div>
      </div>
    </motion.div>
  )
}

export default function DashboardPage() {
  const { user } = useAuthStore()
  const { jobs } = useJobStore()
  const [activeTab, setActiveTab] = useState<FilterTab>("all")
  const [selectedJob, setSelectedJob] = useState<Job | null>(null)
  const [fetchedJobs, setFetchedJobs] = useState<Job[]>([])

  useEffect(() => {
    authFetch("/api/jobs")
      .then((r) => r.json())
      .then((data: Job[]) => setFetchedJobs(data))
      .catch(() => {})
  }, [])

  const allJobs = [...fetchedJobs, ...jobs].reduce<Job[]>((acc, job) => {
    if (!acc.find((j) => j.id === job.id)) {
      acc.push(job)
    }
    return acc
  }, [])

  const totalClips = allJobs.reduce(
    (sum, j) => sum + (j.output_files.length || (j as any).generated_clips?.length || 0),
    0
  )

  const thisMonthClips = allJobs
    .filter((j) => {
      const started = new Date(j.started_at)
      const now = new Date()
      return started.getMonth() === now.getMonth() && started.getFullYear() === now.getFullYear()
    })
    .reduce((sum, j) => sum + (j.output_files.length || (j as any).generated_clips?.length || 0), 0)

  const filteredJobs = allJobs.filter((job) => {
    if (activeTab === "all") return true
    if (activeTab === "running") return job.status === "running" || job.status === "pending"
    return job.status === activeTab
  })

  const selectedClips = selectedJob
    ? (selectedJob.output_files.length > 0
        ? selectedJob.output_files.map((file: string, i: number) => ({
            title: (selectedJob as any).generated_clips?.[i]?.title || `Clip ${i + 1}`,
            priority: (selectedJob as any).generated_clips?.[i]?.priority || 7,
            hook_score: (selectedJob as any).generated_clips?.[i]?.hook_score || 7,
            reliability_score: (selectedJob as any).generated_clips?.[i]?.reliability_score || 0.8,
            duration_seconds: (selectedJob as any).generated_clips?.[i]?.duration_seconds || 45,
            emotional_tone: (selectedJob as any).generated_clips?.[i]?.emotional_tone || "neutral",
            quote_potential: (selectedJob as any).generated_clips?.[i]?.quote_potential || "",
            output_file: file,
          }))
        : (selectedJob as any).generated_clips || [])
    : []

  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <div className="mx-auto max-w-4xl px-5 py-10 sm:px-8">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-[32px] font-semibold tracking-tight text-[#f5f4ef]">
              My Clips
            </h1>
            <p className="mt-1 text-[14px] text-[#8a8880]">
              {user ? `Signed in as ${user.name}` : "Your clip history"}
            </p>
          </div>
          <a
            href="/#generate"
            className="btn-primary flex items-center gap-2"
          >
            <Sparkles className="h-4 w-4" />
            Generate new
          </a>
        </div>

        <div className="mb-6 grid grid-cols-3 gap-4">
          <div className="rounded-xl border border-white/[0.06] bg-[#0e0e0e] p-4">
            <div className="text-[28px] font-semibold text-[#f5f4ef]">{totalClips}</div>
            <div className="text-[12px] text-[#8a8880]">Total clips generated</div>
          </div>
          <div className="rounded-xl border border-white/[0.06] bg-[#0e0e0e] p-4">
            <div className="text-[28px] font-semibold text-[#f5f4ef]">{thisMonthClips}</div>
            <div className="text-[12px] text-[#8a8880]">Clips this month</div>
          </div>
          <div className="rounded-xl border border-white/[0.06] bg-[#0e0e0e] p-4">
            <div className="text-[28px] font-semibold capitalize text-[#ff5722]">
              {user?.plan ?? "free"}
            </div>
            <div className="text-[12px] text-[#8a8880]">Current plan</div>
          </div>
        </div>

        <div className="mb-6 flex gap-1">
          {(["all", "running", "done", "error"] as FilterTab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "rounded-lg px-4 py-2 text-[13px] font-medium transition-colors",
                activeTab === tab
                  ? "bg-[#ff5722] text-[#0a0a0a]"
                  : "text-[#8a8880] hover:bg-white/5 hover:text-[#f5f4ef]"
              )}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>

        {filteredJobs.length === 0 ? (
          <div className="rounded-2xl border border-white/[0.06] bg-[#0e0e0e] p-16 text-center">
            <Video className="mx-auto mb-4 h-12 w-12 text-[#555550]" />
            <h3 className="mb-2 text-[18px] font-semibold text-[#f5f4ef]">No clips yet</h3>
            <p className="mb-6 text-[14px] text-[#8a8880]">
              Generate your first clip from any YouTube video
            </p>
            <a href="/#generate" className="btn-primary inline-flex items-center gap-2">
              Start generating
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredJobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                isActive={selectedJob?.id === job.id}
                onSelect={setSelectedJob}
              />
            ))}
          </div>
        )}

        {selectedJob && selectedClips.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-8"
          >
            <h3 className="mb-4 text-[18px] font-semibold text-[#f5f4ef]">
              Clips from {selectedJob.url}
            </h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {selectedClips
                .filter((c: any) => c.output_file || c.output_path)
                .map((clip: any, i: number) => (
                  <ClipCard
                    key={clip.output_file || clip.id || i}
                    clip={clip}
                    index={i}
                    jobId={selectedJob.id}
                  />
                ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  )
}