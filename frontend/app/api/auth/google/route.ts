import { NextRequest, NextResponse } from "next/server"

function generateState(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
  let nonce = ""
  for (let i = 0; i < 32; i++) {
    nonce += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  return nonce
}

export async function GET(req: NextRequest) {
  const searchParams = req.nextUrl.searchParams
  const mode = searchParams.get("mode") || "login"

  const clientId = process.env.GOOGLE_CLIENT_ID
  const redirectUri = process.env.GOOGLE_REDIRECT_URI || `${req.nextUrl.origin}/api/auth/google/callback`

  if (!clientId) {
    return NextResponse.json({ error: "Google OAuth not configured" }, { status: 500 })
  }

  const nonce = generateState()
  const state = Buffer.from(JSON.stringify({ mode, nonce })).toString("base64url")

  const scope = encodeURIComponent("openid email profile")

  const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=${scope}&state=${encodeURIComponent(state)}&access_type=offline&prompt=consent`

  const response = NextResponse.redirect(authUrl)
  response.cookies.set("oauth_state", nonce, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 5 * 60,
  })

  return response
}