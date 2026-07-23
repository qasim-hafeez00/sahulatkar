// Server-only session/cookie helpers for web-customer's httpOnly-cookie
// session — mirrors apps/web-admin/src/lib/admin-session.ts. The gateway
// signs customer tokens with the same RS256 key pair as admin tokens
// (settings.JWT_PRIVATE_KEY / JWT_PUBLIC_KEY in apps/gateway/src/config.py),
// but the payload is just `{ user_id }` — customers have no roles, so
// there's no admin-style role/permission claim to carry here.
//
// Used by middleware.ts (edge runtime) and the Route Handlers under
// src/app/api/auth/** and src/app/api/gateway/**, so everything here must
// stay edge-safe (jose + fetch only — no Node-only APIs).
import type { JWTPayload } from "jose"
import type { NextResponse } from "next/server"
import { gatewayCookieOptions, maxAgeFromToken, verifyGatewaySession } from "sk-shared-ts"
import { getGatewayBaseUrl } from "@/lib/gateway-config"

export const SESSION_COOKIE = "sk_session"
export const REFRESH_COOKIE = "sk_refresh"
/**
 * Deliberately NOT httpOnly. A cheap, non-sensitive hint ("1" when a session
 * exists, absent otherwise) that client components read to decide what to
 * render (Sign In vs. Log Out, etc.) without a network round trip. It is
 * never trusted for authorization — every protected route (middleware.ts)
 * and every authenticated API call (the /api/gateway proxy) re-verifies the
 * real httpOnly SESSION_COOKIE server-side regardless of this hint.
 */
export const AUTH_HINT_COOKIE = "sk_auth_state"

const ACCESS_FALLBACK_MAX_AGE = 15 * 60 // 15 minutes, matches gateway's JWT_ACCESS_TTL default
const REFRESH_FALLBACK_MAX_AGE = 60 * 60 * 24 // 24 hours, matches gateway's JWT_REFRESH_TTL default

export interface CustomerSessionPayload extends JWTPayload {
  user_id: number
}

/** Verifies signature + expiry of a gateway-issued customer JWT. Returns null on any failure. */
export async function verifyCustomerToken(token: string): Promise<CustomerSessionPayload | null> {
  return verifyGatewaySession<CustomerSessionPayload>(token, "user_id")
}

/** Sets only the (httpOnly) access-token cookie — used after a silent refresh. */
export function setAccessCookie(response: NextResponse, accessToken: string) {
  const maxAge = maxAgeFromToken(accessToken, ACCESS_FALLBACK_MAX_AGE)
  response.cookies.set(SESSION_COOKIE, accessToken, gatewayCookieOptions(maxAge, true))
}

/** Sets access + refresh + the client-readable auth hint — used on login/verify-otp. */
export function setSessionCookies(response: NextResponse, accessToken: string, refreshToken: string) {
  setAccessCookie(response, accessToken)
  const refreshMaxAge = maxAgeFromToken(refreshToken, REFRESH_FALLBACK_MAX_AGE)
  response.cookies.set(REFRESH_COOKIE, refreshToken, gatewayCookieOptions(refreshMaxAge, true))
  // Tied to the refresh token's (longer) lifetime, not the access token's —
  // it represents "this browser has an active session that can be silently
  // refreshed," not "the access token specifically is still fresh."
  response.cookies.set(AUTH_HINT_COOKIE, "1", gatewayCookieOptions(refreshMaxAge, false))
}

export function clearSessionCookies(response: NextResponse) {
  response.cookies.delete(SESSION_COOKIE)
  response.cookies.delete(REFRESH_COOKIE)
  response.cookies.delete(AUTH_HINT_COOKIE)
}

/**
 * Exchanges a refresh token for a new access token directly against the
 * gateway. Used by both middleware.ts (to avoid bouncing a user to /auth/login
 * just because their 15-minute access token expired while they still hold a
 * valid 24-hour refresh token) and the /api/gateway proxy (to transparently
 * retry a request that came back 401), mirroring the silent-refresh-on-401
 * behavior that used to live client-side in api-client.ts.
 */
export async function refreshAccessToken(refreshToken: string): Promise<string | null> {
  try {
    const res = await fetch(`${getGatewayBaseUrl()}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    })
    if (!res.ok) return null
    const data = await res.json()
    return typeof data.access_token === "string" ? data.access_token : null
  } catch {
    return null
  }
}
