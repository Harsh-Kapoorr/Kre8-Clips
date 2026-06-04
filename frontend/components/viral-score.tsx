"use client"

import { motion } from "framer-motion"
import { Share2, Bookmark, MessageCircle, TrendingUp } from "lucide-react"
import { cn } from "@/lib/utils"

export interface ViralScoreCardProps {
  share?: number
  save?: number
  comment?: number
  composite?: number
  compact?: boolean
  className?: string
}

function pct(value: number | undefined): number {
  if (value === undefined || Number.isNaN(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value * 100)))
}

function scoreColor(p: number): string {
  if (p >= 70) return "text-[#10b581]"
  if (p >= 50) return "text-[#f59e0b]"
  if (p >= 30) return "text-[#3b82f6]"
  return "text-[#999]"
}

function barColor(p: number): string {
  if (p >= 70) return "bg-[#10b581]"
  if (p >= 50) return "bg-[#f59e0b]"
  if (p >= 30) return "bg-[#3b82f6]"
  return "bg-[#cfcfcf]"
}

export function ViralScoreCard({
  share = 0,
  save = 0,
  comment = 0,
  composite = 0,
  compact = false,
  className,
}: ViralScoreCardProps) {
  const shareP = pct(share)
  const saveP = pct(save)
  const commentP = pct(comment)
  const compositeP = pct(composite)

  if (compact) {
    return (
      <div
        className={cn(
          "flex items-center gap-1.5 rounded-full bg-black/65 px-2.5 py-1 text-[10px] font-semibold text-white backdrop-blur-md ring-1 ring-white/10",
          className
        )}
      >
        <TrendingUp className="h-3 w-3" />
        <span className={cn(scoreColor(compositeP))}>
          {compositeP}%
        </span>
        <span className="text-white/50">viral</span>
      </div>
    )
  }

  return (
    <div
      className={cn(
        "rounded-xl border border-[rgba(0,0,0,0.07)] bg-white p-3",
        className
      )}
    >
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <TrendingUp className="h-3.5 w-3.5 text-[#0057ff]" />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-[#666]">
            Viral Score
          </span>
        </div>
        <span className={cn("text-base font-bold tabular-nums", scoreColor(compositeP))}>
          {compositeP}%
        </span>
      </div>

      <div className="space-y-1.5">
        <ProbabilityBar
          icon={<Share2 className="h-3 w-3" />}
          label="Share"
          percent={shareP}
        />
        <ProbabilityBar
          icon={<Bookmark className="h-3 w-3" />}
          label="Save"
          percent={saveP}
        />
        <ProbabilityBar
          icon={<MessageCircle className="h-3 w-3" />}
          label="Comment"
          percent={commentP}
        />
      </div>
    </div>
  )
}

function ProbabilityBar({
  icon,
  label,
  percent,
}: {
  icon: React.ReactNode
  label: string
  percent: number
}) {
  return (
    <div>
      <div className="mb-0.5 flex items-center justify-between text-[10px]">
        <span className="flex items-center gap-1 font-medium text-[#666]">
          {icon}
          {label}
        </span>
        <span className="font-mono font-semibold tabular-nums text-[#1b1c1e]">
          {percent}%
        </span>
      </div>
      <div className="h-1 w-full overflow-hidden rounded-full bg-[#f0f0f0]">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className={cn("h-full rounded-full", barColor(percent))}
        />
      </div>
    </div>
  )
}
