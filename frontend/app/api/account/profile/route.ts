import { NextRequest, NextResponse } from "next/server"
import { findUserById } from "@/backend/auth/db"
import { db } from "@/backend/auth/db"

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
  const { name } = body

  if (typeof name !== "string" || name.trim().length === 0) {
    return NextResponse.json({ error: "Name is required" }, { status: 400 })
  }

  const now = new Date().toISOString()
  const stmt = db.prepare("UPDATE users SET name = ?, updated_at = ? WHERE id = ?")
  stmt.run(name.trim(), now, userId)

  return NextResponse.json({ success: true })
}