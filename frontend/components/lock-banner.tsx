"use client"

import { motion, AnimatePresence } from "framer-motion"
import { Lock, AlertTriangle } from "lucide-react"
import { useAuthStore } from "@/store/authStore"
import { isLockedOut, getUpgradeMessage } from "@/lib/plans"
import { cn } from "@/lib/utils"

export function LockBanner() {
  const { user } = useAuthStore()

  if (!user) return null
  if (!isLockedOut(user.plan, user.clips_used)) return null

  const message = getUpgradeMessage(user.plan, user.clips_used)
  if (!message) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        className="w-full border-b border-white/10 bg-[#0e0e0e]"
      >
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8">
          <div className="flex items-center gap-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/5">
              <Lock className="h-5 w-5 text-[#ff7043]" />
            </div>
            <div>
              <p className="text-[14px] font-medium text-[#f5f4ef]">{message}</p>
              <p className="mt-0.5 text-[12px] text-[#8a8880]">
                Upgrade to unlock unlimited clips, or set up BYOK — free forever.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <a
              href="/pricing"
              className="rounded-lg bg-[#ff5722] px-4 py-2 text-[13px] font-semibold text-[#0a0a0a] transition-opacity hover:opacity-90"
            >
              Upgrade to Pro — $19/mo
            </a>
            <a
              href="/account?tab=apikeys"
              className="rounded-lg border border-white/20 px-4 py-2 text-[13px] font-medium text-[#f5f4ef] transition-colors hover:bg-white/5"
            >
              Set up BYOK — free
            </a>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}