"use client"

import { useState } from "react"
import { motion } from "framer-motion"
import { useAuthStore } from "@/store/authStore"
import { PLANS } from "@/lib/plans"
import { cn } from "@/lib/utils"

const PLAN_ORDER: Array<"free" | "byok" | "pro"> = ["free", "byok", "pro"]

const FEATURES = [
  { label: "Generate clips", key: "generate" },
  { label: "Multiple aspect ratios", key: "multi_ratio" },
  { label: "Speaker tracking", key: "speaker_tracking" },
  { label: "Burned-in captions", key: "captions" },
  { label: "Smart narrative", key: "smart_narrative" },
  { label: "API access", key: "api_access" },
]

export default function PricingPage() {
  const { user } = useAuthStore()
  const [annual, setAnnual] = useState(false)

  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-12 text-center"
        >
          <h1 className="mb-4 text-[36px] font-semibold text-[#f5f4ef]">Simple, transparent pricing</h1>
          <p className="text-[16px] text-[#6a6860]">Start free. Upgrade when you need more.</p>

          <div className="mt-6 flex items-center justify-center gap-3">
            <span className={cn("text-[13px]", !annual ? "text-[#f5f4ef]" : "text-[#6a6860]")}>Monthly</span>
            <button
              onClick={() => setAnnual(!annual)}
              className={cn(
                "relative h-5 w-10 rounded-full transition-colors",
                annual ? "bg-[#ff5722]" : "bg-white/10"
              )}
            >
              <div
                className={cn(
                  "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                  annual ? "translate-x-5" : "translate-x-0.5"
                )}
              />
            </button>
            <span className={cn("text-[13px]", annual ? "text-[#f5f4ef]" : "text-[#6a6860]")}>
              Annual <span className="text-[#ffd700]">(-20%)</span>
            </span>
          </div>
        </motion.div>

        <div className="grid gap-6 md:grid-cols-3">
          {PLAN_ORDER.map((planId, index) => {
            const plan = PLANS[planId]
            const isCurrentPlan = user?.plan === planId
            const monthlyPrice = annual && plan.price_usd !== null
              ? Math.round(plan.price_usd * 0.8)
              : plan.price_usd

            return (
              <motion.div
                key={planId}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: index * 0.1 }}
                className={cn(
                  "relative rounded-2xl border p-6 transition-colors",
                  isCurrentPlan
                    ? "border-[#ff5722] bg-[#ff5722]/5"
                    : "border-white/10 bg-white/[0.02] hover:border-white/20"
                )}
              >
                {isCurrentPlan && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-[#ff5722] px-3 py-1 text-[11px] font-semibold text-[#0a0a0a]">
                    Current plan
                  </div>
                )}

                {plan.badge && (
                  <div className="absolute -top-3 right-6 rounded-full bg-[#ffd700] px-3 py-1 text-[11px] font-bold text-[#0a0a0a]">
                    {plan.badge}
                  </div>
                )}

                <div className="mb-6">
                  <h3 className="text-[18px] font-medium text-[#f5f4ef]">{plan.name}</h3>
                  <div className="mt-2 flex items-baseline gap-1">
                    {monthlyPrice === null ? (
                      <span className="text-[28px] font-semibold text-[#f5f4ef]">Free</span>
                    ) : monthlyPrice === 0 ? (
                      <span className="text-[28px] font-semibold text-[#f5f4ef]">$0</span>
                    ) : (
                      <>
                        <span className="text-[28px] font-semibold text-[#f5f4ef]">${monthlyPrice}</span>
                        <span className="text-[14px] text-[#6a6860]">/month</span>
                      </>
                    )}
                  </div>
                  {annual && plan.price_usd !== null && plan.price_usd > 0 && (
                    <p className="mt-1 text-[12px] text-[#6a6860]">
                      ${plan.price_usd} billed monthly
                    </p>
                  )}
                  <p className="mt-2 text-[13px] text-[#6a6860]">
                    {plan.clips_limit === null
                      ? "Unlimited clips"
                      : plan.clips_limit === 1
                      ? "1 free clip, no credit card"
                      : `${plan.clips_limit} clips per month`}
                  </p>
                </div>

                <ul className="mb-6 space-y-2.5">
                  {FEATURES.map((feature) => {
                    const available = plan.features.includes(feature.key)
                    return (
                      <li key={feature.key} className="flex items-center gap-2.5 text-[13px]">
                        {available ? (
                          <svg className="h-4 w-4 text-[#ff5722]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        ) : (
                          <svg className="h-4 w-4 text-[#3a3a38]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        )}
                        <span className={available ? "text-[#b8b6b0]" : "text-[#3a3a38]"}>
                          {feature.label}
                        </span>
                      </li>
                    )
                  })}
                </ul>

                {plan.requires_keys && (
                  <p className="mb-4 text-[12px] text-[#6a6860]">
                    Requires Deepgram + Gemini API keys
                  </p>
                )}

                {isCurrentPlan ? (
                  <div className="w-full rounded-lg border border-white/20 py-2.5 text-center text-[14px] font-medium text-[#6a6860]">
                    Current plan
                  </div>
                ) : planId === "free" ? (
                  <a
                    href="/signup"
                    className="block w-full rounded-lg bg-amber-500 py-2.5 text-center text-[14px] font-semibold text-black transition-opacity hover:bg-amber-400"
                  >
                    Start with 1 free clip →
                  </a>
                ) : planId === "byok" ? (
                  <a
                    href="/account?tab=apikeys"
                    className="block w-full rounded-lg border border-white/20 py-2.5 text-center text-[14px] font-medium text-[#f5f4ef] transition-colors hover:bg-white/5"
                  >
                    Configure BYOK
                  </a>
                ) : (
                  <a
                    href="/account?tab=plan"
                    className="block w-full rounded-lg bg-[#ff5722] py-2.5 text-center text-[14px] font-semibold text-[#0a0a0a] transition-opacity hover:opacity-90"
                  >
                    Upgrade to Pro
                  </a>
                )}
              </motion.div>
            )
          })}
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.4 }}
          className="mt-16 text-center"
        >
          <p className="text-[14px] text-[#6a6860]">
            All plans include access to the Kre8 Clips web app. BYOK requires your own Deepgram and Gemini API keys.
          </p>
        </motion.div>
      </div>
    </div>
  )
}