import { NextRequest, NextResponse } from "next/server"
import { findUserByEmail, createUser } from "@/backend/auth/db"
import { createUserSession } from "@/backend/auth/jwt"

export async function GET(req: NextRequest) {
  const searchParams = req.nextUrl.searchParams
  const code = searchParams.get("code")
  const state = searchParams.get("state") || "login"
  const error = searchParams.get("error")

  if (error) {
    return NextResponse.redirect(new URL(`/?google_error=${encodeURIComponent(error)}`, req.url))
  }

  if (!code) {
    return NextResponse.redirect(new URL("/login?error=missing_code", req.url))
  }

  try {
    const clientId = process.env.GOOGLE_CLIENT_ID
    const clientSecret = process.env.GOOGLE_CLIENT_SECRET
    const redirectUri = process.env.GOOGLE_REDIRECT_URI || `${req.nextUrl.origin}/api/auth/google/callback`

    const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: clientId!,
        client_secret: clientSecret!,
        redirect_uri: redirectUri,
        grant_type: "authorization_code",
      }),
    })

    if (!tokenRes.ok) {
      throw new Error("Failed to exchange code for tokens")
    }

    const tokenData = await tokenRes.json()
    const accessToken = tokenData.access_token

    const userInfoRes = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
      headers: { Authorization: `Bearer ${accessToken}` },
    })

    if (!userInfoRes.ok) {
      throw new Error("Failed to fetch user info")
    }

    const googleUser = await userInfoRes.json()
    const { email, name, sub: googleId } = googleUser

    let user = findUserByEmail(email)

    if (!user) {
      user = createUser(email, null, name || email.split("@")[0], "google", googleId)
    }

    const session = await createUserSession(user.id)
    const redirectUrl = state === "signup" ? "/?just_signed_up=true" : "/?just_logged_in=true"

    const response = NextResponse.redirect(new URL(redirectUrl, req.url))
    response.cookies.set("refresh_token", session.refreshToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 7 * 24 * 60 * 60,
    })

    return response
  } catch (err) {
    console.error("Google OAuth error:", err)
    return NextResponse.redirect(new URL("/login?error=google_auth_failed", req.url))
  }
}