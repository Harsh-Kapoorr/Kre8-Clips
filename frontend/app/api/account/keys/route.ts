import { NextRequest, NextResponse } from "next/server"
import { findUserById, incrementClipsUsed, findUserByEmail } from "@/backend/auth/db"

export async function PUT(request: NextRequest) {
  const userId = request.headers.get("x-user-id")
  if (!userId) {
    return NextResponse.json({ error: "Authentication required" }, { status: 401 })
  }

  const user = findUserById(userId)
  if (!user) {
    return NextResponse.json({ error: "User not found" }, { status: 404 })
  }

  const body = await request.json()
  const { deepgram_key, gemini_key } = body

  if (typeof deepgram_key !== "string" || typeof gemini_key !== "string") {
    return NextResponse.json({ error: "deepgram_key and gemini_key are required" }, { status: 400 })
  }

  const { updateUserApiKeys } = await import("@/backend/auth/db")
  updateUserApiKeys(userId, deepgram_key.trim(), gemini_key.trim())

  return NextResponse.json({ success: true })
}