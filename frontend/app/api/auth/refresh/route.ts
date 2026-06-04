import { NextRequest, NextResponse } from "next/server"
import { refreshUserSession, verifyAccessToken } from "@/backend/auth/jwt"
import { findUserById } from "@/backend/auth/db"

export async function POST(req: NextRequest) {
  const refreshToken = req.cookies.get("refresh_token")?.value
  
  if (!refreshToken) {
    return NextResponse.json({ error: "No refresh token" }, { status: 401 })
  }
  
  const session = await refreshUserSession(refreshToken)
  if (!session) {
    return NextResponse.json({ error: "Invalid or expired refresh token" }, { status: 401 })
  }
  
  const newPayload = await verifyAccessToken(session.accessToken)
  const user = newPayload ? findUserById(newPayload.sub) : null
  
  if (!user) {
    return NextResponse.json({ error: "User not found" }, { status: 404 })
  }
  
  const response = NextResponse.json({ 
    user: { id: user.id, email: user.email, name: user.name, plan: user.plan, clips_used: user.clips_used },
    accessToken: session.accessToken,
  })
  
  response.cookies.set("refresh_token", session.refreshToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 7 * 24 * 60 * 60,
  })
  
  return response
}