import { NextRequest, NextResponse } from "next/server"
import { SESSION_COOKIE, clearSessionCookies } from "@/lib/session"
import { getGatewayBaseUrl } from "@/lib/gateway-config"

// Mirrors apps/web-admin's src/app/api/auth/logout/route.ts: revoke the
// session at the gateway (best-effort) and clear all local session cookies
// regardless of whether that call succeeds.
const GATEWAY_BASE_URL = getGatewayBaseUrl()

export async function POST(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value

  if (token) {
    await fetch(`${GATEWAY_BASE_URL}/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    }).catch(() => {})
  }

  const response = NextResponse.json({ status: "ok" })
  clearSessionCookies(response)
  return response
}
