import { NextRequest, NextResponse } from "next/server"
import { createUser, findUserByEmail } from "@/backend/auth/db"
import { hashPassword } from "@/backend/auth/password"
import { createUserSession } from "@/backend/auth/jwt"

export async function POST(req: NextRequest) {
  try {
    const { email, password, name } = await req.json()
    
    if (!email || !password || !name) {
      return NextResponse.json({ error: "Email, password, and name are required" }, { status: 400 })
    }
    
    if (password.length < 8) {
      return NextResponse.json({ error: "Password must be at least 8 characters" }, { status: 400 })
    }
    
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(email)) {
      return NextResponse.json({ error: "Invalid email format" }, { status: 400 })
    }
    
    const existing = findUserByEmail(email)
    if (existing) {
      return NextResponse.json({ error: "An account with this email already exists" }, { status: 409 })
    }
    
    const passwordHash = await hashPassword(password)
    const user = createUser(email, passwordHash, name)
    const session = await createUserSession(user.id)
    
    const response = NextResponse.json({ user: { id: user.id, email: user.email, name: user.name, plan: user.plan, clips_used: 0 }, accessToken: session.accessToken })
    
    response.cookies.set("refresh_token", session.refreshToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 7 * 24 * 60 * 60,
    })
    
    return response
  } catch (error) {
    console.error("Signup error:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}