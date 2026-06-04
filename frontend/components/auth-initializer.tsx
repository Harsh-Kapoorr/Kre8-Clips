"use client"

import { useEffect } from "react"
import { useAuthStore } from "@/store/authStore"

export function AuthInitializer() {
  const fetchMe = useAuthStore((s) => s.fetchMe)

  useEffect(() => {
    fetchMe()
  }, [fetchMe])

  return null
}