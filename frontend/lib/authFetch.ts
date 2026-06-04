const ACCESS_TOKEN_KEY = "kre8_access_token"

function getToken(): string | null {
  if (typeof window === "undefined") return null
  return sessionStorage.getItem(ACCESS_TOKEN_KEY)
}

function setToken(token: string | null) {
  if (typeof window === "undefined") return
  if (token) {
    sessionStorage.setItem(ACCESS_TOKEN_KEY, token)
  } else {
    sessionStorage.removeItem(ACCESS_TOKEN_KEY)
  }
}

export async function authFetch(path: string, options?: RequestInit): Promise<Response> {
  const token = getToken()

  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string> || {}),
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  let res = await fetch(path, { ...options, headers })

  if (res.status === 401) {
    // Try to refresh
    try {
      const refreshRes = await fetch("/api/auth/refresh", { method: "POST" })
      if (refreshRes.ok) {
        const refreshData = await refreshRes.json()
        if (refreshData.accessToken) {
          setToken(refreshData.accessToken)
          headers["Authorization"] = `Bearer ${refreshData.accessToken}`
          res = await fetch(path, { ...options, headers })
        }
      }
    } catch {}
  }

  return res
}