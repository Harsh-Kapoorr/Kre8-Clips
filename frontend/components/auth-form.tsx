"use client"

import { useState } from "react"
import { motion } from "framer-motion"
import { AuthUser } from "@/store/authStore"

interface AuthFormProps {
  mode: "login" | "signup"
  onSubmit: (data: { email: string; password: string; name?: string }) => Promise<void>
  isLoading: boolean
  error: string | null
  googleLoading?: boolean
  onGoogleSignIn?: () => void
}

export function AuthForm({ mode, onSubmit, isLoading, error, googleLoading, onGoogleSignIn }: AuthFormProps) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [name, setName] = useState("")
  const [emailError, setEmailError] = useState("")
  const [passwordError, setPasswordError] = useState("")

  const validate = () => {
    let valid = true
    setEmailError("")
    setPasswordError("")

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(email)) {
      setEmailError("Please enter a valid email address")
      valid = false
    }

    if (password.length < 8) {
      setPasswordError("Password must be at least 8 characters")
      valid = false
    }

    return valid
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return
    await onSubmit({ email, password, ...(mode === "signup" ? { name } : {}) })
  }

  return (
    <div className="w-full">
      <a href="/" className="flex items-center justify-center gap-2 mb-8">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-[#ff5722]">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="#0a0a0a">
            <polygon points="6 4 20 12 6 20 6 4" />
          </svg>
        </span>
        <span className="text-[16px] font-semibold text-[#f5f4ef]">
          Kre<span className="text-[#ff5722]">8</span> <span className="text-[#8a8880] font-normal">Clips</span>
        </span>
      </a>

      <div
        className="rounded-xl border border-white/5 bg-white/[0.02] p-8"
        style={{ backdropFilter: "blur(20px)" }}
      >
        <h1 className="mb-6 text-center text-[22px] font-semibold text-[#f5f4ef]">
          {mode === "login" ? "Welcome back" : "Create your account"}
        </h1>

        <button
            type="button"
            onClick={onGoogleSignIn}
            disabled={googleLoading || isLoading}
            className="flex w-full items-center justify-center gap-3 rounded-lg border border-white/10 bg-white/5 py-3 text-[14px] font-medium text-[#f5f4ef] transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {googleLoading ? (
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="h-4 w-4" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
            )}
            Continue with Google
          </button>

          <div className="relative flex items-center gap-2 my-4">
            <div className="flex-1 border-t border-white/10" />
            <span className="text-[12px] text-[#5a5858]">or</span>
            <div className="flex-1 border-t border-white/10" />
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
          {mode === "signup" && (
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-[#b8b6b0]">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-[14px] text-[#f5f4ef] placeholder:text-[#5a5858] focus:border-[#ff5722]/50 focus:outline-none focus:ring-1 focus:ring-[#ff5722]/25 transition-colors"
                placeholder="Your name"
              />
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-[13px] font-medium text-[#b8b6b0]">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setEmailError("") }}
              required
              className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-[14px] text-[#f5f4ef] placeholder:text-[#5a5858] focus:border-[#ff5722]/50 focus:outline-none focus:ring-1 focus:ring-[#ff5722]/25 transition-colors"
              placeholder="you@example.com"
            />
            {emailError && (
              <p className="mt-1.5 text-[12px] text-red-400">{emailError}</p>
            )}
          </div>

          <div>
            <label className="mb-1.5 block text-[13px] font-medium text-[#b8b6b0]">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setPasswordError("") }}
              required
              className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-[14px] text-[#f5f4ef] placeholder:text-[#5a5858] focus:border-[#ff5722]/50 focus:outline-none focus:ring-1 focus:ring-[#ff5722]/25 transition-colors"
              placeholder="••••••••"
            />
            {passwordError && (
              <p className="mt-1.5 text-[12px] text-red-400">{passwordError}</p>
            )}
          </div>

          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-[13px] text-red-400">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-lg bg-[#ff5722] py-3 text-[14px] font-semibold text-[#0a0a0a] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Please wait...
              </span>
            ) : mode === "login" ? (
              "Sign in"
            ) : (
              "Create account"
            )}
          </button>
        </form>

        <div className="mt-6 text-center text-[13px] text-[#6a6860]">
          {mode === "login" ? (
            <>
              Don&apos;t have an account?{" "}
              <a href="/signup" className="text-[#ff5722] hover:underline">Sign up</a>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <a href="/login" className="text-[#ff5722] hover:underline">Sign in</a>
            </>
          )}
        </div>
      </div>
    </div>
  )
}