import { NextRequest, NextResponse } from "next/server"
import { clearSession } from "@/backend/auth/jwt"

export async function POST(req: NextRequest) {
  const refreshToken = req.cookies.get("refresh_token")?.value
  
  if (refreshToken) {
    clearSession(refreshToken)
  }
  
  const response = NextResponse.json({ success: true })
  response.cookies.set("refresh_token", "", { path: "/", maxAge: 0 })
  
  return response
}