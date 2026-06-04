"use client"

import { motion, useReducedMotion } from "framer-motion"

const PLATFORMS = [
  "YouTube",
  "TikTok",
  "Instagram Reels",
  "YouTube Shorts",
  "Twitter / X",
  "LinkedIn",
  "Podcasts",
  "Interviews",
  "Keynotes",
  "Tutorials",
]

export function PlatformMarquee() {
  const reduce = useReducedMotion()

  return (
    <section className="border-y border-white/[0.04] py-8 sm:py-10">
      <div className="mx-auto max-w-7xl px-5 sm:px-8">
        <p className="eyebrow mb-6 text-center">
          Optimised for every platform
        </p>
      </div>
      <div
        className="relative overflow-hidden"
        style={{
          maskImage:
            "linear-gradient(90deg, transparent 0, black 8%, black 92%, transparent 100%)",
          WebkitMaskImage:
            "linear-gradient(90deg, transparent 0, black 8%, black 92%, transparent 100%)",
        }}
      >
        {reduce ? (
          <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-4 px-6 text-[#8a8880]">
            {PLATFORMS.map((p) => (
              <span key={p} className="text-[15px] font-medium tracking-tight">
                {p}
              </span>
            ))}
          </div>
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8 }}
            className="marquee-track py-2"
          >
            {[...PLATFORMS, ...PLATFORMS].map((p, i) => (
              <span
                key={`${p}-${i}`}
                className="flex shrink-0 items-center text-[28px] font-semibold tracking-tight text-[#8a8880] sm:text-[36px]"
                style={{ fontFamily: "var(--font-serif)", fontStyle: "italic" }}
              >
                {p}
                <span className="ml-10 text-[#ff5722]">✦</span>
              </span>
            ))}
          </motion.div>
        )}
      </div>
    </section>
  )
}
