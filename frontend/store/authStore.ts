import { create } from "zustand"

export interface AuthUser {
  id: string
  email: string
  name: string
  plan: "free" | "byok" | "pro"
  clips_used: number
}

interface AuthStore {
  user: AuthUser | null
  isLoading: boolean
  accessToken: string | null
  setUser: (user: AuthUser | null, accessToken?: string | null) => void
  logout: () => Promise<void>
  fetchMe: () => Promise<void>
}

const ACCESS_TOKEN_KEY = "kre8_access_token"

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null
  return sessionStorage.getItem(ACCESS_TOKEN_KEY)
}

function setStoredToken(token: string | null) {
  if (typeof window === "undefined") return
  if (token) {
    sessionStorage.setItem(ACCESS_TOKEN_KEY, token)
  } else {
    sessionStorage.removeItem(ACCESS_TOKEN_KEY)
  }
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  isLoading: true,
  accessToken: null,

  setUser: (user, accessToken) => {
    setStoredToken(accessToken ?? null)
    set({ user, accessToken: accessToken ?? null })
  },

  logout: async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" })
    } catch {}
    setStoredToken(null)
    set({ user: null, accessToken: null })
    window.location.href = "/login"
  },

  fetchMe: async () => {
    set({ isLoading: true })

    try {
      const refreshRes = await fetch("/api/auth/refresh", { method: "POST" })
      if (refreshRes.ok) {
        const refreshData = await refreshRes.json()
        if (refreshData.user) {
          get().setUser(refreshData.user, refreshData.accessToken ?? undefined)
          return
        }
      }
    } catch {}

    const token = getStoredToken()
    if (token) {
      try {
        const res = await fetch("/api/auth/me", {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (res.ok) {
          const data = await res.json()
          get().setUser(data.user)
          return
        }
      } catch {}
    }

    set({ user: null, isLoading: false })
  },
}))