"use client"

import { Suspense } from "react"
import { useEffect, useRef, useState } from "react"
import { motion, type Variants, useReducedMotion } from "framer-motion"
import nextDynamic from "next/dynamic"
import { useSearchParams } from "next/navigation"
import {
  ArrowRight,
  ArrowUpRight,
  Brain,
  Mic2,
  Sparkles,
  Zap,
  Layout,
  Workflow,
  Play,
  Wand2,
  Film,
  Quote,
  X,
  ArrowUpDown,
  Download,
} from "lucide-react"
import { useJobStore } from "@/store/useJobStore"
import { useAuthStore } from "@/store/authStore"
import { useToast } from "@/components/toast-provider"
import { GenerationOptions, Job } from "@/types"
import { Header } from "@/components/header"
import { PipelineProgress } from "@/components/pipeline-progress"
import { LivePreview } from "@/components/live-preview"
import { UrlInputForm } from "@/components/url-input-form"
import { OptionsPanel } from "@/components/options-panel"
import { ClipCard } from "@/components/clip-card"

const ProductPreview = nextDynamic(() => import("@/components/product-preview").then((m) => m.ProductPreview), { loading: () => <div className="h-[300px] animate-pulse bg-[#0a0a0a]" /> })
const PlatformMarquee = nextDynamic(() => import("@/components/marquee").then((m) => m.PlatformMarquee))
const SiteFooter = nextDynamic(() => import("@/components/site-footer").then((m) => m.SiteFooter))

const EASE = [0.16, 1, 0.3, 1] as const

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: EASE } },
}

const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.9, ease: EASE } },
}

const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
}

const STEPS = [
  {
    n: "01",
    icon: Play,
    title: "Paste a YouTube URL.",
    body: "Public video, podcast, or keynote. We pull the source and transcribe it in the background.",
  },
  {
    n: "02",
    icon: Wand2,
    title: "AI finds the moments.",
    body: "Gemini scores every segment for hook, body, and payoff — and stitches narrative arcs.",
  },
  {
    n: "03",
    icon: Film,
    title: "Render in any ratio.",
    body: "Vertical, square, widescreen. Speaker-tracked, captioned, beat-synced. Ready to post.",
  },
]

const CAPABILITIES = [
  {
    icon: Brain,
    title: "AI narrative scoring",
    body: "Gemini-powered analysis ranks every segment for hook, body, and payoff potential.",
  },
  {
    icon: Mic2,
    title: "Speaker tracking",
    body: "Kalman-filtered face lock keeps the active speaker centered on vertical crops.",
  },
  {
    icon: Sparkles,
    title: "Smart captions",
    body: "Word-precise captions with pop, fade, and typewriter styles baked in.",
  },
  {
    icon: Zap,
    title: "Beat sync",
    body: "Cut points aligned to natural audio pauses and emphasis — not arbitrary seconds.",
  },
  {
    icon: Layout,
    title: "Every ratio",
    body: "9:16, 1:1, 16:9, 4:5 — all generated from a single render pass.",
  },
  {
    icon: Workflow,
    title: "Narrative assembly",
    body: "Combine hook + body + payoff from different moments into one compelling short.",
  },
]

const STATS = [
  { value: "12×", label: "Faster than manual editing" },
  { value: "94%", label: "Average hook-score accuracy" },
  { value: "<90s", label: "End-to-end pipeline time" },
  { value: "9:16", label: "Native for Reels, Shorts, TikTok" },
]

const TESTIMONIAL = {
  quote:
    "I dropped in a 2-hour podcast and got six ready-to-post clips in under two minutes. The narrative assembly is the kind of thing I didn’t know I needed until I saw it.",
  author: "Maya Reyes",
  role: "Creator · 240k followers",
}

export const dynamic = "force-dynamic"

function HomeInner() {
  const { activeJob, isGenerating, syncFromApi, updateJob } = useJobStore()
  const { user } = useAuthStore()
  const { toast } = useToast()
  const searchParams = useSearchParams()
  const [options, setOptions] = useState<Partial<GenerationOptions>>({})
  const [mounted, setMounted] = useState(false)
  const [bannerDismissed, setBannerDismissed] = useState(false)
  const [sortBy, setSortBy] = useState<"viral" | "newest">("viral")
  const confettiFired = useRef(false)
  const reduce = useReducedMotion()

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (!mounted) return
    const dismissed = sessionStorage.getItem("kre8_banner_dismissed")
    if (dismissed === "1") setBannerDismissed(true)
  }, [mounted])

  useEffect(() => {
    if (!mounted) return
    const justSignedUp = searchParams.get("just_signed_up")
    const justLoggedIn = searchParams.get("just_logged_in")
    if (justSignedUp) {
      toast("success", "Welcome! You have 1 free clip. Paste a URL above to get started.")
      window.history.replaceState({}, "", "/")
    } else if (justLoggedIn) {
      const clips = user?.clips_used ?? 0
      toast("success", `Welcome back! You have ${clips} clips remaining.`)
      window.history.replaceState({}, "", "/")
    }
  }, [mounted, searchParams, toast, user])

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>
    const sync = () => {
      fetch("/api/jobs")
        .then((r) => r.json())
        .then((jobs: Job[]) => syncFromApi(jobs))
        .catch(() => {})
    }
    sync()
    interval = setInterval(sync, 5000)
    return () => clearInterval(interval)
  }, [syncFromApi])

  useEffect(() => {
    if (activeJob?.status === "done" && !isGenerating) {
      const jobId = activeJob.id
      const gc = (activeJob as any).generated_clips
      if (
        (!gc || gc.length === 0 || !gc[0]?.output_path) &&
        activeJob.output_files.length === 0
      ) {
        fetch(`/api/jobs/${jobId}`)
          .then((r) => r.json())
          .then((enrichedJob) => {
            if (enrichedJob && enrichedJob.id) updateJob(jobId, enrichedJob)
          })
          .catch(() => {})
      }
    }
  }, [activeJob?.id, activeJob?.status, isGenerating, updateJob, activeJob])

  const showProgress =
    mounted &&
    isGenerating &&
    (activeJob?.status === "running" || activeJob?.status === "pending")
  const showError =
    mounted && activeJob?.status === "error" && activeJob?.step !== "Cancelled"
  const isCancelled =
    mounted && activeJob?.status === "error" && activeJob?.step === "Cancelled"
  const showNoClips =
    mounted &&
    activeJob?.status === "done" &&
    activeJob.output_files.length === 0 &&
    ((activeJob as any).generated_clips?.length || 0) === 0
  const showResults =
    mounted &&
    activeJob?.status === "done" &&
    (activeJob.output_files.length > 0 || (activeJob as any).generated_clips?.length > 0)

  useEffect(() => {
    if (showResults && !confettiFired.current) {
      confettiFired.current = true
      const duration = 3000
      const end = Date.now() + duration
      const colors = ["#ff5722", "#ff7043", "#f5f4ef", "#ffb547"]

      const frame = () => {
        import("canvas-confetti").then((mod: { default: (opts: object) => void }) => {
          mod.default({ particleCount: 3, angle: 60, spread: 55, origin: { x: 0 }, colors })
          mod.default({ particleCount: 3, angle: 120, spread: 55, origin: { x: 1 }, colors })
        })
        if (Date.now() < end) requestAnimationFrame(frame)
      }
      frame()
    }
    if (!showResults) confettiFired.current = false
  }, [showResults])

  return (
    <div id="top" className="relative">
      <Header />

      {/* ─────────────── SIGNUP BANNER ─────────────── */}
      {!bannerDismissed && (
        <div className="w-full bg-amber-500/10 border-b border-amber-500/20">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-2.5 sm:px-8">
            <p className="text-[13px] text-amber-200">
              <span className="mr-1">🎬</span>
              1 free clip when you sign up. No credit card.
              <a href="/signup" className="ml-2 inline-flex items-center gap-1 font-semibold text-amber-100 hover:text-amber-50">
                Sign up free <ArrowRight className="h-3 w-3" />
              </a>
            </p>
            <button
              onClick={() => {
                sessionStorage.setItem("kre8_banner_dismissed", "1")
                setBannerDismissed(true)
              }}
              className="ml-4 rounded-md p-1 text-amber-400 transition-colors hover:bg-amber-500/20 hover:text-amber-300"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* ─────────────── HERO ─────────────── */}
      <section className="relative overflow-hidden">
        {/* Aurora gradient backdrop */}
        <div className="hero-aurora" aria-hidden="true">
          <div
            className="aurora-orb aurora-a"
            style={{
              top: "-15%",
              left: "-10%",
              width: "640px",
              height: "640px",
              background:
                "radial-gradient(circle, rgba(255,87,34,0.35) 0%, rgba(255,87,34,0) 70%)",
            }}
          />
          <div
            className="aurora-orb aurora-b"
            style={{
              top: "30%",
              right: "-15%",
              width: "560px",
              height: "560px",
              background:
                "radial-gradient(circle, rgba(255,87,34,0.18) 0%, rgba(255,87,34,0) 70%)",
            }}
          />
        </div>

        <div className="relative mx-auto max-w-7xl px-5 pb-16 pt-20 sm:px-8 sm:pb-24 sm:pt-28 lg:pt-36">
          <motion.div
            initial="hidden"
            animate="show"
            variants={stagger}
            className="mx-auto max-w-4xl text-center"
          >

            <motion.h1
              variants={fadeUp}
              className="text-balance text-[44px] font-semibold leading-[0.98] tracking-[-0.035em] text-[#f5f4ef] sm:text-[68px] lg:text-[88px]"
            >
              Long videos into{" "}
              <span className="serif-italic text-[#ff5722]">viral moments.</span>
            </motion.h1>

            <motion.p
              variants={fadeUp}
              className="mx-auto mt-7 max-w-xl text-balance text-[16px] leading-relaxed text-[#b8b6b0] sm:text-[18px]"
            >
              Paste a YouTube URL. Kre8 Clips finds the hook, builds the narrative,
              and renders platform-ready shorts in under ninety seconds.
            </motion.p>
          </motion.div>

          {/* Inline hero form */}
          <motion.div
            id="generate"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.4, ease: EASE }}
            className="mx-auto mt-10 max-w-2xl sm:mt-12"
          >
            <UrlInputForm options={options} />
            <div className="mt-4 flex justify-center">
              <OptionsPanel options={options} onChange={setOptions} />
            </div>
          </motion.div>

          {/* Inline states */}
          {showProgress && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="mx-auto mt-10 max-w-3xl"
            >
              <PipelineProgress />
              <div className="mt-4">
                <LivePreview />
              </div>
            </motion.div>
          )}
          {showError && (
            <StatusCard
              className="mx-auto mt-8 max-w-2xl"
              tone="error"
              title="Generation failed"
              body={
                activeJob?.error
                  ? activeJob.error.includes("No clips identified")
                    ? "No clips found. Try a different video or adjust the prompt."
                    : activeJob.error
                  : "Something went wrong. Try again."
              }
            />
          )}
          {isCancelled && (
            <StatusCard
              className="mx-auto mt-8 max-w-2xl"
              tone="muted"
              title="Generation cancelled"
              body="The job was stopped before completion. Submit a new URL to try again."
            />
          )}
          {showNoClips && (
            <StatusCard
              className="mx-auto mt-8 max-w-2xl"
              tone="warn"
              title="No clips found"
              body={
                activeJob?.step_detail ||
                "We couldn’t find engaging moments in this video. Try a different one, change the duration range, or adjust the prompt."
              }
            />
          )}

          {showResults && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mx-auto mt-12 max-w-6xl"
            >
              <div className="mb-5 flex items-end justify-between">
                <div>
                  <h2 className="text-[28px] font-semibold tracking-tight text-[#f5f4ef]">
                    Your clips
                  </h2>
                  <span className="text-[13px] text-[#8a8880]">
                    {(activeJob as any).generated_clips?.length ||
                      activeJob.output_files.length}{" "}
                    ready
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setSortBy((s) => (s === "viral" ? "newest" : "viral"))}
                    className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-[12px] font-medium text-[#b8b6b0] transition-colors hover:border-white/[0.18] hover:text-[#f5f4ef]"
                  >
                    <ArrowUpDown className="h-3.5 w-3.5" />
                    {sortBy === "viral" ? "Top viral" : "Newest"}
                  </button>
                  <button
                    onClick={() => {
                      const clips = (activeJob.output_files.length > 0
                        ? activeJob.output_files.map((file: string, i: number) => ({
                            src: `/api/output/.jobs/${activeJob.id}/${file.split("/").pop()}`,
                            name: (activeJob as any).generated_clips?.[i]?.title || `Clip ${i + 1}`,
                          }))
                        : (activeJob as any).generated_clips?.map((c: any) => ({
                            src: c.output_file || c.output_path,
                            name: c.title,
                          })) || [])
                      clips.forEach((clip: any, idx: number) => {
                        setTimeout(() => {
                          if (clip.src) {
                            const a = document.createElement("a")
                            a.href = clip.src.startsWith("/") ? clip.src : `/api/output/${clip.src}`
                            a.download = (clip.name || "clip").replace(/[^a-zA-Z0-9_-]/g, "_") + ".mp4"
                            document.body.appendChild(a)
                            a.click()
                            document.body.removeChild(a)
                          }
                        }, idx * 300)
                      })
                    }}
                    className="flex items-center gap-1.5 rounded-lg bg-[#ff5722] px-3 py-2 text-[12px] font-semibold text-[#0a0a0a] transition-colors hover:bg-[#ff7043]"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Download all
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {(activeJob.output_files.length > 0
                  ? activeJob.output_files.map((file: string, i: number) => ({
                      title:
                        (activeJob as any).generated_clips?.[i]?.title ||
                        `Clip ${i + 1}`,
                      priority:
                        (activeJob as any).generated_clips?.[i]?.priority || 7,
                      hook_score:
                        (activeJob as any).generated_clips?.[i]?.hook_score || 7,
                      reliability_score:
                        (activeJob as any).generated_clips?.[i]
                          ?.reliability_score || 0.8,
                      duration_seconds:
                        (activeJob as any).generated_clips?.[i]
                          ?.duration_seconds || 45,
                      emotional_tone:
                        (activeJob as any).generated_clips?.[i]?.emotional_tone ||
                        "neutral",
                      quote_potential:
                        (activeJob as any).generated_clips?.[i]?.quote_potential ||
                        "",
                      output_file: file,
                      viral_composite: (activeJob as any).generated_clips?.[i]?.viral_composite || 0,
                    }))
                  : (activeJob as any).generated_clips?.length > 0
                  ? (activeJob as any).generated_clips
                  : []
                )
                  .filter((c: any) => c.output_file || c.output_path)
                  .sort((a: any, b: any) => {
                    if (sortBy === "viral") {
                      return (b.viral_composite || 0) - (a.viral_composite || 0)
                    }
                    return 0
                  })
                  .map((clip: any, i: number) => (
                    <ClipCard
                      key={clip.output_file || clip.id || i}
                      clip={clip}
                      index={i}
                    />
                  ))}
              </div>
            </motion.div>
          )}

          {/* Floating product preview */}
          {!showProgress && !showResults && (
            <motion.div
              initial={{ opacity: 0, y: 60, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 1, delay: 0.55, ease: EASE }}
              className="mx-auto mt-16 max-w-5xl sm:mt-20"
            >
              <div
                className="aurora-orb"
                style={{
                  position: "absolute",
                  left: "50%",
                  top: "80%",
                  transform: "translateX(-50%)",
                  width: "60%",
                  height: "320px",
                  background:
                    "radial-gradient(ellipse, rgba(255,87,34,0.20) 0%, transparent 70%)",
                  filter: "blur(80px)",
                  zIndex: -1,
                  pointerEvents: "none",
                }}
                aria-hidden="true"
              />
              <ProductPreview />
            </motion.div>
          )}
        </div>
      </section>

      {/* ─────────────── PLATFORM MARQUEE ─────────────── */}
      <PlatformMarquee />

      {/* ─────────────── STATS ─────────────── */}
      <section className="section">
        <div className="mx-auto max-w-7xl px-5 sm:px-8">
          <motion.div
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.3 }}
            variants={stagger}
            className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.04] lg:grid-cols-4"
          >
            {STATS.map((stat) => (
              <motion.div
                key={stat.label}
                variants={fadeUp}
                className="bg-[#0a0a0a] p-6 sm:p-8"
              >
                <div
                  className="text-[44px] font-semibold leading-none tracking-[-0.03em] text-[#f5f4ef] sm:text-[56px]"
                  style={{ fontFamily: "var(--font-serif)" }}
                >
                  {stat.value}
                </div>
                <div className="mt-3 text-[12.5px] leading-relaxed text-[#8a8880]">
                  {stat.label}
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ─────────────── HOW IT WORKS ─────────────── */}
      <section id="how" className="section">
        <div className="mx-auto max-w-7xl px-5 sm:px-8">
          <div className="mb-16 flex flex-col items-start justify-between gap-6 sm:mb-20 sm:flex-row sm:items-end">
            <div>
              <p className="eyebrow mb-4">Process</p>
              <h2 className="max-w-xl text-balance text-[36px] font-semibold leading-[1.05] tracking-[-0.025em] text-[#f5f4ef] sm:text-[52px]">
                From URL to{" "}
                <span className="serif-italic text-[#ff5722]">ready-to-post</span>{" "}
                in three moves.
              </h2>
            </div>
            <p className="max-w-sm text-[15px] leading-relaxed text-[#b8b6b0]">
              No timeline scrubbing. No Premiere. No expensive editor. Just paste
              and ship.
            </p>
          </div>

          <motion.div
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.2 }}
            variants={stagger}
            className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.04] md:grid-cols-3"
          >
            {STEPS.map((step) => (
              <motion.div
                key={step.n}
                variants={fadeUp}
                className="group bg-[#0a0a0a] p-8 transition-colors hover:bg-[#0e0e0e] sm:p-10"
              >
                <div className="mb-10 flex items-center justify-between">
                  <span
                    className="text-[14px] font-semibold tabular text-[#ff5722]"
                    style={{ fontFamily: "var(--font-mono)" }}
                  >
                    {step.n}
                  </span>
                  <step.icon
                    className="h-5 w-5 text-[#8a8880] transition-colors group-hover:text-[#ff5722]"
                  />
                </div>
                <h3 className="mb-3 text-[24px] font-semibold leading-tight tracking-[-0.02em] text-[#f5f4ef]">
                  {step.title}
                </h3>
                <p className="text-[14.5px] leading-relaxed text-[#8a8880]">
                  {step.body}
                </p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ─────────────── CAPABILITIES ─────────────── */}
      <section id="product" className="section">
        <div className="mx-auto max-w-7xl px-5 sm:px-8">
          <div className="mb-16 grid grid-cols-1 gap-10 sm:mb-20 lg:grid-cols-[1fr_1.4fr]">
            <div>
              <p className="eyebrow mb-4">Capabilities</p>
              <h2 className="text-balance text-[36px] font-semibold leading-[1.05] tracking-[-0.025em] text-[#f5f4ef] sm:text-[52px]">
                A complete <span className="serif-italic">post-production</span>{" "}
                pipeline in one URL.
              </h2>
            </div>
            <p className="self-end text-[16px] leading-relaxed text-[#b8b6b0] sm:text-[18px]">
              Every step that used to take an editor hours — transcription,
              analysis, reframing, captions, beat alignment — happens
              automatically in the time it takes to make a coffee.
            </p>
          </div>

          <motion.div
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.1 }}
            variants={stagger}
            className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.04] sm:grid-cols-2 lg:grid-cols-3"
          >
            {CAPABILITIES.map((c) => (
              <motion.div
                key={c.title}
                variants={fadeUp}
                className="group relative bg-[#0a0a0a] p-7 transition-colors hover:bg-[#0e0e0e] sm:p-9"
              >
                <div
                  className="mb-7 inline-flex h-10 w-10 items-center justify-center rounded-md border border-white/[0.08] text-[#ff5722]"
                  style={{ background: "rgba(255,87,34,0.06)" }}
                >
                  <c.icon className="h-4.5 w-4.5" />
                </div>
                <h3 className="mb-2 text-[18px] font-semibold tracking-[-0.015em] text-[#f5f4ef]">
                  {c.title}
                </h3>
                <p className="text-[14px] leading-relaxed text-[#8a8880]">
                  {c.body}
                </p>
                <ArrowUpRight
                  className="absolute right-6 top-6 h-4 w-4 text-[#555550] transition-all group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-[#ff5722]"
                />
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ─────────────── TESTIMONIAL ─────────────── */}
      <section className="section">
        <div className="mx-auto max-w-4xl px-5 sm:px-8">
          <motion.figure
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.8, ease: EASE }}
            className="text-center"
          >
            <Quote
              className="mx-auto mb-8 h-7 w-7 text-[#ff5722]"
              strokeWidth={1.5}
            />
            <blockquote
              className="text-balance text-[28px] font-medium leading-[1.25] tracking-[-0.02em] text-[#f5f4ef] sm:text-[40px]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              “{TESTIMONIAL.quote}”
            </blockquote>
            <figcaption className="mt-10 flex items-center justify-center gap-3">
              <div
                className="flex h-10 w-10 items-center justify-center rounded-full text-[13px] font-semibold text-[#0a0a0a]"
                style={{ background: "#ff5722" }}
              >
                MR
              </div>
              <div className="text-left">
                <div className="text-[14px] font-semibold text-[#f5f4ef]">
                  {TESTIMONIAL.author}
                </div>
                <div className="text-[12.5px] text-[#8a8880]">
                  {TESTIMONIAL.role}
                </div>
              </div>
            </figcaption>
          </motion.figure>
        </div>
      </section>

      {/* ─────────────── CTA BAND ─────────────── */}
      <section className="px-5 pb-24 sm:px-8 sm:pb-32">
        <div className="mx-auto max-w-7xl">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.9, ease: EASE }}
            className="relative overflow-hidden rounded-3xl px-8 py-20 sm:px-16 sm:py-28"
            style={{
              background:
                "linear-gradient(135deg, #1a1a1a 0%, #0a0a0a 60%, #0a0a0a 100%)",
              border: "1px solid rgba(255, 87, 34, 0.18)",
            }}
          >
            <div
              className="aurora-orb"
              style={{
                position: "absolute",
                top: "-30%",
                right: "-10%",
                width: "500px",
                height: "500px",
                background:
                  "radial-gradient(circle, rgba(255,87,34,0.35) 0%, transparent 70%)",
                filter: "blur(100px)",
                pointerEvents: "none",
              }}
              aria-hidden="true"
            />
            <div className="relative mx-auto max-w-2xl text-center">
              <p className="eyebrow-accent mb-6">Ready when you are</p>
              <h2 className="text-balance text-[40px] font-semibold leading-[1.05] tracking-[-0.025em] text-[#f5f4ef] sm:text-[60px]">
                Make your first{" "}
                <span className="serif-italic text-[#ff5722]">viral clip</span>{" "}
                today.
              </h2>
              <p className="mx-auto mt-5 max-w-md text-[15px] leading-relaxed text-[#b8b6b0] sm:text-[16px]">
                Paste a YouTube URL above. We&apos;ll handle the rest — hook
                detection, narrative assembly, render, captions, the lot.
              </p>
              <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
                <a href="/signup" className="btn-primary group">
                  Start free — 1 clip
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                </a>
                <a href="#how" className="btn-ghost">
                  See how it works
                </a>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      <SiteFooter />
    </div>
  )
}

function StatusCard({
  className,
  tone,
  title,
  body,
}: {
  className?: string
  tone: "error" | "warn" | "muted"
  title: string
  body: string
}) {
  const colors = {
    error: "#ff5722",
    warn: "#ffb547",
    muted: "#b8b6b0",
  } as const

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className={className}
    >
      <div
        className="rounded-xl border p-5 text-center"
        style={{
          background: "rgba(255, 255, 255, 0.02)",
          borderColor: `${colors[tone]}30`,
        }}
      >
        <p
          className="mb-1.5 text-[13px] font-semibold"
          style={{ color: colors[tone] }}
        >
          {title}
        </p>
        <p className="text-[13px] leading-relaxed text-[#8a8880]">{body}</p>
      </div>
    </motion.div>
  )
}

export default function Home() {
  return (
    <Suspense>
      <HomeInner />
    </Suspense>
  )
}
