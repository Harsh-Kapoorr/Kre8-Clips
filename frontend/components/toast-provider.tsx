"use client"

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  type ReactNode,
} from "react"
import { motion, AnimatePresence } from "framer-motion"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

export type ToastType = "success" | "error" | "info" | "warning"

interface Toast {
  id: string
  type: ToastType
  message: string
}

interface ToastContextValue {
  toast: (type: ToastType, message: string) => void
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} })

const TOAST_COLORS: Record<ToastType, { border: string; icon: string }> = {
  success: { border: "border-l-[#22c55e]", icon: "text-[#22c55e]" },
  error: { border: "border-l-[#ef4444]", icon: "text-[#ef4444]" },
  info: { border: "border-l-[#f59e0b]", icon: "text-[#f59e0b]" },
  warning: { border: "border-l-[#3b82f6]", icon: "text-[#3b82f6]" },
}

const TOAST_ICONS: Record<ToastType, string> = {
  success: "✓",
  error: "✕",
  info: "◆",
  warning: "▲",
}

const MAX_VISIBLE = 3
const AUTO_DISMISS_MS = 4000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const queue = useRef<Toast[]>([])

  const addToast = useCallback((type: ToastType, message: string) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`
    const newToast: Toast = { id, type, message }

    setToasts((prev) => {
      const updated = [...prev, newToast].slice(-MAX_VISIBLE)
      return updated
    })

    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
      if (queue.current.length > 0) {
        const next = queue.current.shift()
        if (next) addToast(next.type, next.message)
      }
    }, AUTO_DISMISS_MS)
  }, [])

  const toast = useCallback(
    (type: ToastType, message: string) => {
      setToasts((prev) => {
        if (prev.length >= MAX_VISIBLE) {
          queue.current.push({ id: "", type, message } as unknown as Toast)
          return prev
        }
        addToast(type, message)
        return prev
      })
    },
    [addToast]
  )

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
        <AnimatePresence>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, x: 40, scale: 0.95 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 40, scale: 0.95 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className={cn(
                "flex w-72 items-start gap-3 rounded-xl border border-white/10 bg-[#141414] p-4 shadow-xl",
                "border-l-4",
                TOAST_COLORS[t.type].border
              )}
            >
              <span className={cn("mt-0.5 text-[16px]", TOAST_COLORS[t.type].icon)}>
                {TOAST_ICONS[t.type]}
              </span>
              <p className="flex-1 text-[13px] leading-snug text-[#e0dfd8]">
                {t.message}
              </p>
              <button
                onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
                className="mt-0.5 text-[#6a6860] transition-colors hover:text-[#b8b6b0]"
              >
                <X className="h-4 w-4" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}