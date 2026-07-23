import { NextRequest, NextResponse } from "next/server"
import { setSessionCookies } from "@/lib/session"
import { getGatewayBaseUrl } from "@/lib/gateway-config"

// Proxies the customer login form's phone/password to the gateway and, on
// success, sets the access + refresh tokens as httpOnly cookies here — the
// browser never sees the raw JWTs. Mirrors apps/web-admin's
// src/app/api/auth/login/route.ts, adjusted for the gateway's customer
// AuthResponse shape (access_token + refresh_token, no admin role/temp-token
// onboarding states).
const GATEWAY_BASE_URL = getGatewayBaseUrl()

export async function POST(request: NextRequest) {
  const body = await request.json()

  const gatewayResponse = await fetch(`${GATEWAY_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  })

  const data = await gatewayResponse.json().catch(() => ({}))

  if (!gatewayResponse.ok) {
    return NextResponse.json(
      { status: "error", message: typeof data.detail === "string" ? data.detail : "Login failed" },
      { status: gatewayResponse.status }
    )
  }

  const response = NextResponse.json({ status: "ok", user_id: data.user_id, kyc_status: data.kyc_status })
  setSessionCookies(response, data.access_token, data.refresh_token)
  return response
}
