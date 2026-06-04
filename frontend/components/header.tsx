"use client"

import { useState, useRef, useEffect } from "react"
import { motion } from "framer-motion"
import { useJobStore } from "@/store/useJobStore"
import { useAuthStore } from "@/store/authStore"

const NAV = [
  { label: "Product", href: "#product" },
  { label: "How it works", href: "#how" },
  { label: "Pricing", href: "#pricing" },
  { label: "Docs", href: "#docs" },
]

function UserAvatar({ name, plan }: { name: string; plan: string }) {
  const initials = name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2)

  return (
    <div className="relative">
      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#ff5722] text-[12px] font-semibold text-[#0a0a0a]">
        {initials}
      </div>
      {plan === "pro" && (
        <div className="absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-[#ffd700] text-[8px] font-bold text-[#0a0a0a]">
          P
        </div>
      )}
    </div>
  )
}

export function Header() {
  const activeJob = useJobStore((s) => s.activeJob)
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const generating = activeJob?.status === "running" || activeJob?.status === "pending"
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
      className="sticky top-0 z-50 w-full"
    >
      <div
        className="w-full"
        style={{
          background: "rgba(10, 10, 10, 0.65)",
          backdropFilter: "blur(20px) saturate(180%)",
          WebkitBackdropFilter: "blur(20px) saturate(180%)",
          borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
        }}
      >
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8">
          <motion.a
            href="#top"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="flex items-center gap-2"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-[#ff5722]">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="#0a0a0a" aria-hidden="true">
                <polygon points="6 4 20 12 6 20 6 4" />
              </svg>
            </span>
            <span className="text-[15px] font-semibold tracking-tight text-[#f5f4ef]">
              Kre<span style={{ color: "#ff5722" }}>8</span>{" "}
              <span className="text-[#8a8880] font-normal">Clips</span>
            </span>
          </motion.a>

          <nav className="hidden items-center gap-8 md:flex">
            {NAV.map((item) => (
              <a
                key={item.label}
                href={item.href}
                className="text-[13px] font-medium text-[#b8b6b0] transition-colors hover:text-[#f5f4ef]"
              >
                {item.label}
              </a>
            ))}
          </nav>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="flex items-center gap-2 sm:gap-3"
          >
            {generating && (
              <div className="hidden items-center gap-1.5 text-[12px] text-[#ff5722] sm:flex">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#ff5722] opacity-75" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#ff5722]" />
                </span>
                <span className="font-medium">{activeJob?.step}</span>
              </div>
            )}

            {user ? (
              <div className="relative" ref={dropdownRef}>
                <button
                  onClick={() => setDropdownOpen((v) => !v)}
                  className="flex items-center gap-2 rounded-lg px-3 py-2 transition-colors hover:bg-white/5"
                >
                  <UserAvatar name={user.name} plan={user.plan} />
                  <span className="hidden text-[13px] font-medium text-[#f5f4ef] sm:block">{user.name}</span>
                  <svg
                    className={`h-4 w-4 text-[#6a6860] transition-transform ${dropdownOpen ? "rotate-180" : ""}`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {dropdownOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.15 }}
                    className="absolute right-0 top-full mt-2 w-48 rounded-lg border border-white/10 bg-[#1a1a1a] py-1 shadow-xl"
                  >
                    <div className="px-4 py-2 border-b border-white/5">
                      <p className="text-[13px] font-medium text-[#f5f4ef]">{user.name}</p>
                      <p className="text-[12px] text-[#6a6860]">{user.email}</p>
                    </div>
                    <a
                      href="/account"
                      className="flex items-center gap-2 px-4 py-2 text-[13px] text-[#b8b6b0] hover:bg-white/5 hover:text-[#f5f4ef]"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                      My Account
                    </a>
                    <a
                      href="/dashboard"
                      className="flex items-center gap-2 px-4 py-2 text-[13px] text-[#b8b6b0] hover:bg-white/5 hover:text-[#f5f4ef]"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                      </svg>
                      Dashboard
                    </a>
                    <div className="my-1 border-t border-white/5" />
                    <button
                      onClick={() => { setDropdownOpen(false); logout() }}
                      className="flex w-full items-center gap-2 px-4 py-2 text-[13px] text-red-400 hover:bg-white/5"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                      </svg>
                      Sign out
                    </button>
                  </motion.div>
                )}
              </div>
            ) : (
              <>
                <a href="/login" className="text-[13px] font-medium text-[#b8b6b0] transition-colors hover:text-[#f5f4ef]">
                  Sign in
                </a>
                <a href="#generate" className="btn-primary !py-2 !text-[13px]">
                  Get started
                </a>
              </>
            )}
          </motion.div>
        </div>
      </div>
    </motion.header>
  )
}