import { NextRequest, NextResponse } from "next/server"
import { setSessionCookies } from "@/lib/session"
import { getGatewayBaseUrl } from "@/lib/gateway-config"

// Proxies OTP verification (used by both the register and OTP-login flows —
// see src/app/auth/otp/page.tsx) to the gateway and, on success, sets the
// httpOnly session cookies here instead of returning tokens to the browser.
const GATEWAY_BASE_URL = getGatewayBaseUrl()

export async function POST(request: NextRequest) {
  const body = await request.json()

  const gatewayResponse = await fetch(`${GATEWAY_BASE_URL}/auth/verify-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  })

  const data = await gatewayResponse.json().catch(() => ({}))

  if (!gatewayResponse.ok) {
    return NextResponse.json(
      { status: "error", message: typeof data.detail === "string" ? data.detail : "Verification failed" },
      { status: gatewayResponse.status }
    )
  }

  const response = NextResponse.json({ status: "ok", user_id: data.user_id, kyc_status: data.kyc_status })
  setSessionCookies(response, data.access_token, data.refresh_token)
  return response
}
