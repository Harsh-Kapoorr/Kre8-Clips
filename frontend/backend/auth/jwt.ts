import { SignJWT, jwtVerify } from "jose"
import { createSession, findSessionByToken, deleteSession, findUserById } from "./db"

const JWT_SECRET = new TextEncoder().encode(
  process.env.JWT_SECRET || "kre8-clips-secret-change-in-production-min-32-chars"
)

const ACCESS_TOKEN_TTL = "15m"

function generateRefreshToken(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
  let token = ""
  for (let i = 0; i < 64; i++) {
    token += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  return token
}

export async function signAccessToken(user: { id: string; email: string; name: string; plan: string; clips_used: number }): Promise<string> {
  return new SignJWT({ sub: user.id, email: user.email, name: user.name, plan: user.plan, clips_used: user.clips_used })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(ACCESS_TOKEN_TTL)
    .sign(JWT_SECRET)
}

export async function verifyAccessToken(token: string): Promise<{ sub: string; email: string; name: string; plan: string; clips_used: number } | null> {
  try {
    const { payload } = await jwtVerify(token, JWT_SECRET)
    return payload as any
  } catch {
    return null
  }
}

export async function createUserSession(userId: string) {
  const refreshToken = generateRefreshToken()
  const user = findUserById(userId)
  if (!user) throw new Error("User not found")
  const session = createSession(userId, refreshToken)
  return {
    accessToken: await signAccessToken(user),
    refreshToken,
    expiresAt: session.expiresAt,
  }
}

export async function refreshUserSession(refreshToken: string) {
  const session = findSessionByToken(refreshToken)
  if (!session) return null
  
  const user = findUserById(session.user_id)
  if (!user) return null
  
  deleteSession(refreshToken)
  return createUserSession(session.user_id)
}

export function clearSession(refreshToken: string) {
  deleteSession(refreshToken)
}