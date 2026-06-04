import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

const JWT_SECRET = new TextEncoder().encode(
  process.env.JWT_SECRET || "kre8-clips-secret-change-in-production-min-32-chars"
)

const PROTECTED_PATHS = ["/api/jobs/"]

async function verifyAccessToken(token: string): Promise<{ sub: string; email: string; name: string; plan: string; clips_used: number } | null> {
  try {
    const { jwtVerify } = await import("jose")
    const { payload } = await jwtVerify(token, JWT_SECRET)
    return payload as any
  } catch {
    return null
  }
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  
  const needsAuth = PROTECTED_PATHS.some(p => pathname.startsWith(p))
  
  if (needsAuth) {
    const token = request.headers.get("authorization")?.replace("Bearer ", "")
    if (!token) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
    }
    
    const payload = await verifyAccessToken(token)
    if (!payload) {
      return NextResponse.json({ error: "Invalid or expired token" }, { status: 401 })
    }
    
    const headers = new Headers(request.headers)
    headers.set("x-user-id", payload.sub as string)
    headers.set("x-user-email", payload.email as string)
    headers.set("x-user-plan", payload.plan as string)
    headers.set("x-user-clips-used", String(payload.clips_used))
    
    return NextResponse.next({ request: { headers } })
  }
  
  return NextResponse.next()
}

export const config = {
  matcher: ["/api/jobs/:path*"],
}