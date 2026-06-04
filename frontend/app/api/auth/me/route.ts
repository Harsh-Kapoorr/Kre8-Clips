import { NextRequest, NextResponse } from "next/server"
import { verifyAccessToken } from "@/backend/auth/jwt"
import { findUserById } from "@/backend/auth/db"

export async function GET(req: NextRequest) {
  const token = req.headers.get("authorization")?.replace("Bearer ", "")
  
  if (!token) {
    return NextResponse.json({ error: "No token provided" }, { status: 401 })
  }
  
  const payload = await verifyAccessToken(token)
  if (!payload) {
    return NextResponse.json({ error: "Invalid or expired token" }, { status: 401 })
  }
  
  const user = findUserById(payload.sub)
  if (!user) {
    return NextResponse.json({ error: "User not found" }, { status: 404 })
  }
  
  return NextResponse.json({ 
    user: { id: user.id, email: user.email, name: user.name, plan: user.plan, clips_used: user.clips_used } 
  })
}