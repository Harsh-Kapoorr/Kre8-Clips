"use client"

import { motion, useReducedMotion } from "framer-motion"
import { Play, Sparkles, Mic2, Captions, Layers, Zap } from "lucide-react"

const SAMPLE_CLIPS = [
  {
    n: "01",
    title: "The contrarian take on AI agents",
    score: 9.2,
    duration: "0:42",
    tone: "Bold",
  },
  {
    n: "02",
    title: "Why most creators burn out by month 6",
    score: 8.7,
    duration: "0:58",
    tone: "Reflective",
  },
  {
    n: "03",
    title: "Three signals you’re undercharging",
    score: 8.4,
    duration: "0:35",
    tone: "Direct",
  },
]

const CAPABILITIES = [
  { icon: Sparkles, label: "Gemini narrative scoring" },
  { icon: Mic2, label: "Speaker tracking" },
  { icon: Captions, label: "Animated captions" },
  { icon: Layers, label: "9:16 · 1:1 · 16:9 · 4:5" },
]

export function ProductPreview() {
  const reduce = useReducedMotion()

  return (
    <div
      className="relative w-full overflow-hidden rounded-2xl"
      style={{
        background: "linear-gradient(180deg, #131313 0%, #0a0a0a 100%)",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        boxShadow:
          "0 1px 0 rgba(255,255,255,0.04) inset, 0 50px 100px -20px rgba(0,0,0,0.6), 0 30px 60px -30px rgba(255,87,34,0.15)",
      }}
    >
      {/* Window chrome */}
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]/60" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]/60" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]/60" />
        </div>
        <div
          className="flex items-center gap-2 rounded-md px-3 py-1 text-[11px]"
          style={{
            background: "rgba(255,255,255,0.04)",
            color: "#8a8880",
            fontFamily: "var(--font-mono)",
          }}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-[#ff5722]" />
          kre8clips.ai / jobs / 2h-podcast-with-lex
        </div>
        <div className="w-12" />
      </div>

      <div className="grid grid-cols-1 gap-0 lg:grid-cols-[1fr_360px]">
        {/* ── Player + timeline ── */}
        <div className="border-b border-white/[0.06] lg:border-b-0 lg:border-r">
          {/* Video surface */}
          <div className="relative aspect-video w-full overflow-hidden">
            <div
              className="absolute inset-0"
              style={{
                background:
                  "radial-gradient(ellipse at 30% 40%, #1f1f1f 0%, #0a0a0a 70%)",
              }}
            />
            <div
              className="absolute inset-0"
              style={{
                backgroundImage:
                  "linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px)",
                backgroundSize: "32px 32px",
              }}
            />
            <div className="absolute inset-0 flex items-center justify-center">
              <div
                className="flex h-14 w-14 items-center justify-center rounded-full backdrop-blur-md"
                style={{
                  background: "rgba(255,87,34,0.95)",
                  boxShadow:
                    "0 0 0 8px rgba(255,87,34,0.15), 0 8px 32px rgba(255,87,34,0.4)",
                }}
              >
                <Play className="ml-0.5 h-5 w-5 fill-[#0a0a0a] text-[#0a0a0a]" />
              </div>
            </div>

            {/* Timecode + speaker */}
            <div className="absolute left-4 top-4 flex items-center gap-2">
              <span
                className="rounded-sm bg-black/60 px-1.5 py-0.5 text-[10px] font-medium tabular text-[#f5f4ef] backdrop-blur-sm"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                00:14:32 / 02:08:17
              </span>
              <span className="rounded-sm bg-[#ff5722]/90 px-1.5 py-0.5 text-[10px] font-semibold text-[#0a0a0a]">
                LIVE TRACKING
              </span>
            </div>

            {/* Speaker face indicator */}
            <div className="absolute right-4 top-4">
              <div
                className="h-10 w-10 rounded-full"
                style={{
                  background:
                    "linear-gradient(135deg, #2a2a2a 0%, #1a1a1a 100%)",
                  border: "2px solid #ff5722",
                  boxShadow: "0 0 0 4px rgba(255,87,34,0.15)",
                }}
              />
            </div>

            {/* Caption preview */}
            <div className="absolute inset-x-0 bottom-6 flex justify-center px-6">
              <div className="max-w-md text-center">
                <p
                  className="inline-block rounded-md bg-[#ff5722] px-3 py-1.5 text-[18px] font-bold leading-tight text-[#0a0a0a]"
                >
                  the market doesn’t reward
                  <br />
                  <span className="serif-italic text-[20px]">consistency</span>
                  <span className="text-[#0a0a0a]">.</span> it rewards hooks.
                </p>
              </div>
            </div>
          </div>

          {/* Timeline */}
          <div className="px-4 py-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[#8a8880]">
                Timeline · 9 clips detected
              </span>
              <span
                className="text-[10px] tabular text-[#8a8880]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                2h 08m
              </span>
            </div>
            <div className="relative h-12 rounded-md bg-[#131313]">
              {/* Waveform-like bars */}
              <div className="absolute inset-0 flex items-center gap-[2px] overflow-hidden rounded-md px-1">
                {Array.from({ length: 120 }).map((_, i) => {
                  const seed = (i * 9301 + 49297) % 233280
                  const h = 20 + (seed % 70)
                  const isHighlight = i > 22 && i < 32
                  return (
                    <span
                      key={i}
                      className="block w-[2px] rounded-full"
                      style={{
                        height: `${h}%`,
                        background: isHighlight
                          ? "#ff5722"
                          : "rgba(255,255,255,0.18)",
                        opacity: isHighlight ? 0.95 : 0.6,
                      }}
                    />
                  )
                })}
              </div>
              {/* Highlight region for the active clip */}
              <div
                className="absolute top-0 h-full rounded-md"
                style={{
                  left: "18%",
                  width: "8%",
                  background: "rgba(255,87,34,0.10)",
                  border: "1px solid #ff5722",
                  boxShadow: "0 0 0 1px rgba(255,87,34,0.2)",
                }}
              />
              {/* Playhead */}
              <div
                className="absolute top-0 h-full w-px"
                style={{
                  left: "22%",
                  background: "#f5f4ef",
                  boxShadow: "0 0 8px rgba(245,244,239,0.5)",
                }}
              />
            </div>
          </div>
        </div>

        {/* ── Side: generated clips ── */}
        <div className="bg-[#0e0e0e] p-4 sm:p-5">
          <div className="mb-4 flex items-center justify-between">
            <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[#8a8880]">
              Generated · Ready to ship
            </span>
            <Zap className="h-3.5 w-3.5 text-[#ff5722]" />
          </div>
          <div className="space-y-2">
            {SAMPLE_CLIPS.map((clip, i) => (
              <motion.div
                key={clip.n}
                initial={reduce ? false : { opacity: 0, x: 12 }}
                whileInView={reduce ? undefined : { opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.1, ease: [0.16, 1, 0.3, 1] }}
                className="group rounded-lg p-3 transition-colors"
                style={{
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid rgba(255,255,255,0.05)",
                }}
              >
                <div className="mb-2 flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className="text-[10px] font-bold tabular text-[#8a8880]"
                      style={{ fontFamily: "var(--font-mono)" }}
                    >
                      {clip.n}
                    </span>
                    <p className="truncate text-[12.5px] font-medium leading-tight text-[#f5f4ef]">
                      {clip.title}
                    </p>
                  </div>
                </div>
                <div className="flex items-center justify-between text-[10px]">
                  <div className="flex items-center gap-2 text-[#8a8880]">
                    <span
                      className="tabular"
                      style={{ fontFamily: "var(--font-mono)" }}
                    >
                      {clip.duration}
                    </span>
                    <span>·</span>
                    <span>{clip.tone}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span
                      className="font-semibold tabular"
                      style={{ fontFamily: "var(--font-mono)", color: "#ff5722" }}
                    >
                      {clip.score}
                    </span>
                    <span className="text-[#8a8880]">hook</span>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>

      {/* Capability strip */}
      <div
        className="grid grid-cols-2 gap-px sm:grid-cols-4"
        style={{ background: "rgba(255,255,255,0.04)" }}
      >
        {CAPABILITIES.map((c) => (
          <div
            key={c.label}
            className="flex items-center gap-2 bg-[#0a0a0a] px-4 py-3 text-[11.5px] text-[#b8b6b0]"
          >
            <c.icon className="h-3.5 w-3.5 text-[#ff5722]" />
            <span>{c.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
