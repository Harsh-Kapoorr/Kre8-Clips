"use client"

import { useState, useRef, useCallback, useEffect } from "react"
import { motion } from "framer-motion"
import {
  Play,
  Pause,
  Volume2,
  VolumeX,
  Download,
  Clock,
  ThumbsUp,
  ThumbsDown,
  Quote,
  Share2,
  Copy,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { ViralScoreCard } from "./viral-score"

interface ClipCardProps {
  clip: {
    id?: string
    title: string
    priority?: number
    hook_score?: number
    reliability_score?: number
    duration_seconds: number
    emotional_tone?: string
    quote_potential?: string
    output_file?: string
    output_path?: string
    segments?: Array<{
      start: string
      end: string
      start_seconds: number
      end_seconds: number
    }>
    viral_share_prob?: number
    viral_save_prob?: number
    viral_comment_prob?: number
    viral_composite?: number
    render_error?: string
    render_traceback?: string
  }
  index: number
  jobId?: string
}

type FeedbackState = "up" | "down" | null

export function ClipCard({ clip, index, jobId }: ClipCardProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const seekBarRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [videoInView, setVideoInView] = useState(false)

  const [isPlaying, setIsPlaying] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(clip.duration_seconds || 0)
  const [feedback, setFeedback] = useState<FeedbackState>(null)
  const [feedbackPending, setFeedbackPending] = useState(false)
  const [isScrubbing, setIsScrubbing] = useState(false)
  const wasPlayingRef = useRef(false)

  const compositePct = Math.round((clip.viral_composite ?? 0) * 100)
  const scoreColor =
    compositePct >= 70
      ? "text-[#10b581] bg-[#10b581]/15 ring-[#10b581]/30"
      : compositePct >= 50
      ? "text-[#f59e0b] bg-[#f59e0b]/15 ring-[#f59e0b]/30"
      : compositePct >= 30
      ? "text-[#3b82f6] bg-[#3b82f6]/15 ring-[#3b82f6]/30"
      : "text-[#999] bg-[#f0f0f0] ring-[#e0e0e0]"

  const formatDuration = (seconds: number) => {
    const secs = Math.max(0, Math.floor(seconds || 0))
    const mins = Math.floor(secs / 60)
    const s = secs % 60
    return `${mins}:${s.toString().padStart(2, "0")}`
  }

  const srcPath = clip.output_file || clip.output_path || ""
  const videoSrc = srcPath
    ? (() => {
        const p = srcPath
        if (
          p.startsWith("/Users/") ||
          p.startsWith("/C:") ||
          p.match(/^[A-Z]:/i)
        ) {
          const match = p.match(/\/.jobs\/([^/]+)\/(.+)$/)
          if (match) {
            const filename = match[2].replace(/ /g, "_")
            return `/api/output/.jobs/${match[1]}/${filename}`
          }
        }
        if (p.startsWith("/.jobs/") || p.startsWith(".jobs/")) {
          const clean = p.replace(/^\//, "").replace("/.jobs/", "/jobs/")
          return `/api/output/${clean}`
        }
        if (p.startsWith("/output/") || p.startsWith("output/")) {
          return `/api/output/${p.replace(/^\//, "")}`
        }
        return `/api/output/${p.replace(/^\//, "")}`
      })()
    : null

  const handlePlayPause = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    if (v.paused || v.ended) {
      v.play().catch(() => {})
    } else {
      v.pause()
    }
  }, [])

  const handleMuteToggle = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    v.muted = !v.muted
    setIsMuted(v.muted)
  }, [])

  const positionToTime = useCallback(
    (clientX: number): number | null => {
      const v = videoRef.current
      const bar = seekBarRef.current
      if (!v || !bar || !duration) return null
      const rect = bar.getBoundingClientRect()
      if (rect.width <= 0) return null
      const pct = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
      return pct * duration
    },
    [duration]
  )

  const seekToClientX = useCallback(
    (clientX: number) => {
      const v = videoRef.current
      const t = positionToTime(clientX)
      if (!v || t === null) return
      v.currentTime = t
      setCurrentTime(t)
    },
    [positionToTime]
  )

  const handleSeek = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      seekToClientX(e.clientX)
    },
    [seekToClientX]
  )

  const handleSeekPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (e.button !== 0 && e.pointerType === "mouse") return
      const v = videoRef.current
      if (!v) return
      e.preventDefault()
      seekBarRef.current?.setPointerCapture(e.pointerId)
      wasPlayingRef.current = !v.paused && !v.ended
      if (wasPlayingRef.current) v.pause()
      setIsScrubbing(true)
      seekToClientX(e.clientX)
    },
    [seekToClientX]
  )

  const handleSeekKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const v = videoRef.current
      if (!v) return
      const big = e.shiftKey ? 10 : 5
      const small = 1
      let next: number | null = null
      switch (e.key) {
        case "ArrowLeft":
        case "ArrowDown":
          next = Math.max(0, v.currentTime - big)
          break
        case "ArrowRight":
        case "ArrowUp":
          next = Math.min(duration, v.currentTime + big)
          break
        case "PageDown":
          next = Math.max(0, v.currentTime - 10)
          break
        case "PageUp":
          next = Math.min(duration, v.currentTime + 10)
          break
        case "Home":
          next = 0
          break
        case "End":
          next = duration
          break
        case " ":
        case "Enter":
          e.preventDefault()
          handlePlayPause()
          return
        default:
          return
      }
      if (next === null || !Number.isFinite(duration) || duration <= 0) return
      e.preventDefault()
      const clamped = Math.max(0, Math.min(duration, next))
      v.currentTime = clamped
      setCurrentTime(clamped)
    },
    [duration, handlePlayPause]
  )

  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    const onTimeUpdate = () => setCurrentTime(v.currentTime || 0)
    const onLoadedMeta = () => {
      if (Number.isFinite(v.duration) && v.duration > 0) {
        setDuration(v.duration)
      }
    }
    const onPlay = () => setIsPlaying(true)
    const onPause = () => setIsPlaying(false)
    const onEnded = () => setIsPlaying(false)
    const onVolumeChange = () => setIsMuted(v.muted)

    v.addEventListener("timeupdate", onTimeUpdate)
    v.addEventListener("loadedmetadata", onLoadedMeta)
    v.addEventListener("play", onPlay)
    v.addEventListener("pause", onPause)
    v.addEventListener("ended", onEnded)
    v.addEventListener("volumechange", onVolumeChange)
    return () => {
      v.removeEventListener("timeupdate", onTimeUpdate)
      v.removeEventListener("loadedmetadata", onLoadedMeta)
      v.removeEventListener("play", onPlay)
      v.removeEventListener("pause", onPause)
      v.removeEventListener("ended", onEnded)
      v.removeEventListener("volumechange", onVolumeChange)
    }
  }, [videoSrc])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        setVideoInView(entry.isIntersecting)
      },
      { threshold: 0.1 }
    )
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!isScrubbing) return
    const onMove = (e: PointerEvent) => {
      e.preventDefault()
      seekToClientX(e.clientX)
    }
    const onUp = (e: PointerEvent) => {
      const v = videoRef.current
      const bar = seekBarRef.current
      if (bar && bar.hasPointerCapture(e.pointerId)) {
        bar.releasePointerCapture(e.pointerId)
      }
      setIsScrubbing(false)
      if (v && wasPlayingRef.current) {
        v.play().catch(() => {})
      }
      wasPlayingRef.current = false
    }
    document.addEventListener("pointermove", onMove)
    document.addEventListener("pointerup", onUp)
    document.addEventListener("pointercancel", onUp)
    return () => {
      document.removeEventListener("pointermove", onMove)
      document.removeEventListener("pointerup", onUp)
      document.removeEventListener("pointercancel", onUp)
    }
  }, [isScrubbing, seekToClientX])

  const progressPct = duration > 0 ? (currentTime / duration) * 100 : 0

  const handleDownload = () => {
    if (videoSrc) {
      const a = document.createElement("a")
      a.href = videoSrc
      a.download = (srcPath || "clip.mp4").split("/").pop() || "clip.mp4"
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    }
  }

  const submitFeedback = useCallback(
    async (label: "up" | "down") => {
      if (!clip.id) return
      setFeedbackPending(true)
      setFeedback(label)
      try {
        await fetch("/api/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            clip_id: clip.id,
            job_id: jobId,
            label,
            source: "user_thumbs",
          }),
        })
      } catch {
        // Feedback is best-effort; we don't block the UI on it.
      } finally {
        setFeedbackPending(false)
      }
    },
    [clip.id, jobId]
  )

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1, duration: 0.4, ease: "easeOut" }}
      className="card group overflow-hidden transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg"
    >
      <div ref={containerRef} className="relative aspect-[9/16] w-full overflow-hidden bg-[#0a0a0a]">
        {videoSrc ? (
          <>
            {videoInView ? (
            <video
              ref={videoRef}
              src={videoSrc}
              muted={isMuted}
              loop
              playsInline
              preload="metadata"
              className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
            />
            ) : (
              <div className="h-full w-full flex items-center justify-center">
                <div className="h-14 w-14 rounded-full bg-white/10 animate-pulse" />
              </div>
            )}

            <button
              type="button"
              aria-label={isPlaying ? "Pause" : "Play"}
              onClick={handlePlayPause}
              className={cn(
                "absolute inset-0 flex items-center justify-center bg-black/25 transition-opacity duration-200",
                isPlaying
                  ? "opacity-0 hover:opacity-100 focus-visible:opacity-100"
                  : "opacity-100"
              )}
            >
              <span
                className={cn(
                  "flex h-14 w-14 items-center justify-center rounded-full bg-white/25 text-white backdrop-blur-md ring-1 ring-white/30 transition-transform",
                  "group-hover:scale-105"
                )}
              >
                {isPlaying ? (
                  <Pause className="h-6 w-6" fill="white" />
                ) : (
                  <Play className="h-6 w-6 translate-x-[1px]" fill="white" />
                )}
              </span>
            </button>

            <button
              type="button"
              aria-label={isMuted ? "Unmute" : "Mute"}
              onClick={handleMuteToggle}
              className="absolute right-3 top-3 flex h-9 w-9 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur-md ring-1 ring-white/15 transition-colors hover:bg-black/75"
            >
              {isMuted ? (
                <VolumeX className="h-4 w-4" />
              ) : (
                <Volume2 className="h-4 w-4" />
              )}
            </button>

            <div className="absolute inset-x-0 bottom-0 flex flex-col gap-1.5 bg-gradient-to-t from-black/80 via-black/30 to-transparent p-3">
              <div
                ref={seekBarRef}
                role="slider"
                aria-label="Progress"
                aria-valuemin={0}
                aria-valuemax={duration || 0}
                aria-valuenow={Math.round(currentTime * 10) / 10}
                aria-valuetext={`${formatDuration(currentTime)} of ${formatDuration(duration)}`}
                aria-orientation="horizontal"
                tabIndex={0}
                onPointerDown={handleSeekPointerDown}
                onClick={handleSeek}
                onKeyDown={handleSeekKeyDown}
                className="group/seek relative h-1.5 w-full cursor-pointer touch-none select-none rounded-full bg-white/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0057ff]/70"
              >
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-[#0057ff]"
                  style={{ width: `${progressPct}%` }}
                />
                <div
                  className={cn(
                    "absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow transition-opacity",
                    isScrubbing
                      ? "opacity-100"
                      : "opacity-0 group-hover/seek:opacity-100"
                  )}
                  style={{ left: `${progressPct}%` }}
                />
              </div>
              <div
                aria-hidden="true"
                className="flex items-center justify-between font-mono text-[10px] tabular-nums text-white/90"
              >
                <span>{formatDuration(currentTime)}</span>
                <span>{formatDuration(duration)}</span>
              </div>
              <span className="sr-only" aria-live="polite" aria-atomic="true">
                {`${formatDuration(currentTime)} of ${formatDuration(duration)}`}
              </span>
            </div>
          </>
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-4 text-center">
            <div className="text-3xl opacity-30">⚠️</div>
            <p className="text-xs font-medium text-white/80">Render failed</p>
            {clip.render_error && (
              <p className="line-clamp-4 max-w-full break-words font-mono text-[10px] leading-snug text-white/50">
                {clip.render_error}
              </p>
            )}
          </div>
        )}

        <div className="absolute left-3 top-3">
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ring-1",
              scoreColor
            )}
          >
            {compositePct}% viral
          </span>
        </div>

        <div className="absolute bottom-12 right-3 flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-mono font-medium text-white backdrop-blur-sm">
          <Clock className="h-2.5 w-2.5" />
          {formatDuration(duration || clip.duration_seconds)}
        </div>
      </div>

      <div className="p-4">
        <h3 className="mb-2 line-clamp-2 text-sm font-semibold text-[#1b1c1e] leading-snug">
          {clip.title || "Untitled Clip"}
        </h3>

        <ViralScoreCard
          share={clip.viral_share_prob}
          save={clip.viral_save_prob}
          comment={clip.viral_comment_prob}
          composite={clip.viral_composite}
          className="mb-3"
        />

        {clip.emotional_tone && (
          <div className="mb-3 flex flex-wrap gap-1.5">
            <span className="rounded-full bg-[#f5f5f5] px-2 py-0.5 text-[10px] text-[#666]">
              {clip.emotional_tone}
            </span>
            {clip.reliability_score && (
              <span className="rounded-full bg-[#0057ff]/10 px-2 py-0.5 text-[10px] text-[#0057ff]">
                {Math.round(clip.reliability_score * 100)}% reliable
              </span>
            )}
          </div>
        )}

        {clip.quote_potential && (
          <div className="mb-3 flex items-start gap-2 rounded-lg bg-[#f5f5f5] p-2">
            <Quote className="mt-0.5 h-3 w-3 flex-shrink-0 text-[#ccc]" />
            <p className="text-[10px] italic text-[#999] line-clamp-2">
              &ldquo;{clip.quote_potential}&rdquo;
            </p>
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={handleDownload}
            disabled={!videoSrc}
            className={cn(
              "flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-all",
              videoSrc
                ? "bg-[#0057ff] text-white shadow-[0_4px_14px_rgba(0,87,255,0.25)] hover:bg-[#337dff] hover:shadow-[0_6px_20px_rgba(0,87,255,0.35)]"
                : "cursor-not-allowed bg-[#f5f5f5] text-[#999]"
            )}
          >
            <Download className="h-4 w-4" />
            Download
          </button>

          {clip.id && (
            <div className="flex gap-1">
              <button
                onClick={() => {
                  if (videoSrc) {
                    navigator.clipboard.writeText(window.location.origin + "/?clip=" + clip.id).catch(() => {})
                  }
                }}
                aria-label="Copy share link"
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-[rgba(0,0,0,0.07)] bg-white text-[#666] transition-colors hover:border-[#0057ff] hover:text-[#0057ff]"
              >
                <Share2 className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => {
                  if (clip.title) {
                    navigator.clipboard.writeText(clip.title).catch(() => {})
                  }
                }}
                aria-label="Copy title"
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-[rgba(0,0,0,0.07)] bg-white text-[#666] transition-colors hover:border-[#0057ff] hover:text-[#0057ff]"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => submitFeedback("up")}
                disabled={feedbackPending}
                aria-label="Mark this clip as good"
                className={cn(
                  "flex h-9 w-9 items-center justify-center rounded-lg border transition-colors",
                  feedback === "up"
                    ? "border-[#10b581] bg-[#10b581] text-white"
                    : "border-[rgba(0,0,0,0.07)] bg-white text-[#666] hover:border-[#10b581] hover:text-[#10b581]"
                )}
              >
                <ThumbsUp className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => submitFeedback("down")}
                disabled={feedbackPending}
                aria-label="Mark this clip as bad"
                className={cn(
                  "flex h-9 w-9 items-center justify-center rounded-lg border transition-colors",
                  feedback === "down"
                    ? "border-[#f43f5e] bg-[#f43f5e] text-white"
                    : "border-[rgba(0,0,0,0.07)] bg-white text-[#666] hover:border-[#f43f5e] hover:text-[#f43f5e]"
                )}
              >
                <ThumbsDown className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  )
}
