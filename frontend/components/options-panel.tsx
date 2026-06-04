"use client"

import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { ChevronDown, Settings2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { GenerationOptions } from "@/types"

interface OptionsPanelProps {
  options: Partial<GenerationOptions>
  onChange: (options: Partial<GenerationOptions>) => void
}

const ASPECT_RATIOS = [
  { value: "9:16", label: "9:16" },
  { value: "16:9", label: "16:9" },
  { value: "1:1", label: "1:1" },
  { value: "4:5", label: "4:5" },
] as const

const CAPTION_STYLES = [
  { value: "pop", label: "Pop" },
  { value: "fade", label: "Fade" },
  { value: "typewriter", label: "Typewriter" },
  { value: "none", label: "None" },
] as const

export function OptionsPanel({ options, onChange }: OptionsPanelProps) {
  const [isOpen, setIsOpen] = useState(false)

  const updateOption = <K extends keyof GenerationOptions>(
    key: K,
    value: GenerationOptions[K]
  ) => {
    onChange({ ...options, [key]: value })
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: 0.3 }}
      className="w-full"
    >
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="group flex items-center gap-2 text-[12px] text-[#8a8880] transition-colors hover:text-[#f5f4ef]"
      >
        <Settings2 className="h-3.5 w-3.5" />
        <span className="font-medium">Fine-tune output</span>
        <motion.span
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.25 }}
        >
          <ChevronDown className="h-3.5 w-3.5" />
        </motion.span>
      </button>

      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="mt-6 space-y-6 rounded-xl border border-white/[0.06] bg-[#0e0e0e] p-5 sm:p-6">
              <Field label="Prompt">
                <textarea
                  value={options.prompt || ""}
                  onChange={(e) => updateOption("prompt", e.target.value)}
                  placeholder="Find engaging narrative moments with a clear hook, body, and satisfying payoff."
                  rows={3}
                  className="w-full resize-none rounded-md border border-white/[0.08] bg-[#0a0a0a] px-3 py-2.5 text-[13px] text-[#f5f4ef] placeholder-[#555550] outline-none transition-colors focus:border-[#ff5722]"
                />
              </Field>

              <Field label="Aspect ratio">
                <div className="grid grid-cols-4 gap-2">
                  {ASPECT_RATIOS.map((r) => (
                    <button
                      key={r.value}
                      type="button"
                      onClick={() =>
                        updateOption("aspect_ratio", r.value as GenerationOptions["aspect_ratio"])
                      }
                      className={cn(
                        "rounded-md border px-3 py-2.5 text-[12px] font-semibold transition-all",
                        options.aspect_ratio === r.value
                          ? "border-[#ff5722] text-[#ff5722]"
                          : "border-white/[0.08] text-[#b8b6b0] hover:border-white/[0.18]"
                      )}
                      style={{
                        background:
                          options.aspect_ratio === r.value
                            ? "rgba(255,87,34,0.08)"
                            : "rgba(255,255,255,0.02)",
                      }}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </Field>

              <Field label="Number of clips">
                <div className="grid grid-cols-10 gap-1.5">
                  {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => updateOption("num_clips", n)}
                      className={cn(
                        "rounded-md border py-2 text-[12px] font-bold transition-all",
                        options.num_clips === n
                          ? "border-[#ff5722] text-[#0a0a0a]"
                          : "border-white/[0.08] text-[#b8b6b0] hover:border-white/[0.18]"
                      )}
                      style={{
                        background:
                          options.num_clips === n
                            ? "#ff5722"
                            : "rgba(255,255,255,0.02)",
                      }}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </Field>

              <Field
                label="Duration"
                right={
                  <span
                    className="text-[11px] tabular text-[#b8b6b0]"
                    style={{ fontFamily: "var(--font-mono)" }}
                  >
                    {options.min_duration || 20}s — {options.max_duration || 65}s
                  </span>
                }
              >
                <div className="flex gap-3">
                  <input
                    type="range"
                    min={5}
                    max={120}
                    value={options.min_duration || 20}
                    onChange={(e) =>
                      updateOption(
                        "min_duration",
                        Math.min(Number(e.target.value), (options.max_duration || 65) - 5)
                      )
                    }
                    className="flex-1 accent-[#ff5722]"
                  />
                  <input
                    type="range"
                    min={5}
                    max={120}
                    value={options.max_duration || 65}
                    onChange={(e) =>
                      updateOption(
                        "max_duration",
                        Math.max(Number(e.target.value), (options.min_duration || 20) + 5)
                      )
                    }
                    className="flex-1 accent-[#ff5722]"
                  />
                </div>
              </Field>

              <Field label="Features">
                <div className="space-y-2">
                  {[
                    { key: "speaker_tracking" as const, label: "Speaker tracking", desc: "Follow the active speaker with Kalman-filtered face lock." },
                    { key: "captions" as const, label: "Burn captions", desc: "Overlay word-precise animated captions on the clip." },
                    { key: "narrative" as const, label: "Narrative mode", desc: "Assemble full narratives from multiple segments." },
                    { key: "smart_narrative" as const, label: "Smart narrative", desc: "AI picks hook + body + payoff from different moments." },
                  ].map((item) => (
                    <label
                      key={item.key}
                      className="flex cursor-pointer items-center justify-between gap-4 rounded-md border border-white/[0.06] bg-white/[0.02] p-3 transition-colors hover:bg-white/[0.04]"
                    >
                      <div className="min-w-0">
                        <div className="text-[13px] font-semibold text-[#f5f4ef]">
                          {item.label}
                        </div>
                        <div className="mt-0.5 text-[11.5px] text-[#8a8880]">
                          {item.desc}
                        </div>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={options[item.key] ? "true" : "false"}
                        data-on={options[item.key] ? "true" : "false"}
                        onClick={() => updateOption(item.key, !options[item.key])}
                        className="switch shrink-0"
                      />
                    </label>
                  ))}
                </div>
              </Field>

              {options.captions && (
                <Field label="Caption style">
                  <div className="flex flex-wrap gap-2">
                    {CAPTION_STYLES.map((style) => (
                      <button
                        key={style.value}
                        type="button"
                        onClick={() =>
                          updateOption(
                            "caption_style",
                            style.value as GenerationOptions["caption_style"]
                          )
                        }
                        className={cn(
                          "rounded-md border px-3 py-2 text-[12px] font-semibold transition-all",
                          options.caption_style === style.value
                            ? "border-[#ff5722] text-[#ff5722]"
                            : "border-white/[0.08] text-[#b8b6b0] hover:border-white/[0.18]"
                        )}
                        style={{
                          background:
                            options.caption_style === style.value
                              ? "rgba(255,87,34,0.08)"
                              : "rgba(255,255,255,0.02)",
                        }}
                      >
                        {style.label}
                      </button>
                    ))}
                  </div>
                </Field>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

function Field({
  label,
  right,
  children,
}: {
  label: string
  right?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between">
        <label className="eyebrow">{label}</label>
        {right}
      </div>
      {children}
    </div>
  )
}
