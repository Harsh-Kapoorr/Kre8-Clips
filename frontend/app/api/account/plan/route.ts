import { NextRequest, NextResponse } from "next/server"
import { findUserById, updateUserPlan } from "@/backend/auth/db"

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
  const { plan } = body

  if (plan !== "byok" && plan !== "pro") {
    return NextResponse.json({ error: "Invalid plan. Must be 'byok' or 'pro'" }, { status: 400 })
  }

  updateUserPlan(userId, plan)

  return NextResponse.json({ success: true, plan })
}