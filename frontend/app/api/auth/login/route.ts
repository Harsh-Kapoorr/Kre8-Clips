import { NextRequest, NextResponse } from "next/server"
import { findUserByEmail } from "@/backend/auth/db"
import { verifyPassword } from "@/backend/auth/password"
import { createUserSession } from "@/backend/auth/jwt"

const loginAttempts = new Map<string, { count: number; resetAt: number }>()
const MAX_ATTEMPTS = 5
const WINDOW_MS = 60 * 1000

function checkRateLimit(ip: string): boolean {
  const now = Date.now()
  const attempt = loginAttempts.get(ip)
  
  if (!attempt || now > attempt.resetAt) {
    loginAttempts.set(ip, { count: 1, resetAt: now + WINDOW_MS })
    return true
  }
  
  if (attempt.count >= MAX_ATTEMPTS) {
    return false
  }
  
  attempt.count++
  return true
}

export async function POST(req: NextRequest) {
  const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0] || "unknown"
  
  if (!checkRateLimit(clientIp)) {
    return NextResponse.json({ error: "Too many requests. Please try again later." }, { status: 429 })
  }
  
  try {
    const { email, password } = await req.json()
    
    if (!email || !password) {
      return NextResponse.json({ error: "Email and password are required" }, { status: 400 })
    }
    
    const user = findUserByEmail(email)
    if (!user) {
      return NextResponse.json({ error: "Invalid email or password" }, { status: 401 })
    }

    if (user.provider === "google" && !user.password_hash) {
      return NextResponse.json({ error: "Please sign in with Google" }, { status: 401 })
    }

    const valid = await verifyPassword(password, user.password_hash)
    if (!valid) {
      return NextResponse.json({ error: "Invalid email or password" }, { status: 401 })
    }
    
    const session = await createUserSession(user.id)
    
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
  } catch (error) {
    console.error("Login error:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}