import { NextRequest, NextResponse } from "next/server";
import { decodeJwt } from "jose";
import { ADMIN_SESSION_COOKIE } from "@/lib/admin-session";
import { getGatewayBaseUrl } from "@/lib/gateway-config";

const GATEWAY_BASE_URL = getGatewayBaseUrl();

function setSessionCookie(response: NextResponse, token: string) {
  let maxAge = 15 * 60;
  try {
    const decoded = decodeJwt(token);
    if (typeof decoded.exp === "number") {
      maxAge = Math.max(decoded.exp - Math.floor(Date.now() / 1000), 60);
    }
  } catch {
    // fall back to the 15-minute default above
  }
  response.cookies.set(ADMIN_SESSION_COOKIE, token, {
    httpOnly: true,
    // See packages/shared-ts/src/session.ts::gatewayCookieOptions for why
    // this isn't just `NODE_ENV === "production"` — a production-optimized
    // build can still be served over plain HTTP with no TLS termination
    // (e.g. local Docker Compose), in which case a Secure cookie is
    // silently dropped by the browser and login appears to fail with no
    // error. COOKIE_INSECURE is an explicit opt-out; real deployments never
    // set it.
    secure: process.env.NODE_ENV === "production" && process.env.COOKIE_INSECURE !== "true",
    sameSite: "lax",
    path: "/",
    maxAge,
  });
}

export async function POST(request: NextRequest) {
  const body = await request.json();

  const gatewayResponse = await fetch(`${GATEWAY_BASE_URL}/admin/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (gatewayResponse.ok) {
    const data = await gatewayResponse.json();
    const response = NextResponse.json({ status: "ok", role: data.role, admin_id: data.admin_id });
    setSessionCookie(response, data.access_token);
    return response;
  }

  const detail = await gatewayResponse.json().catch(() => ({ detail: gatewayResponse.statusText }));
  const tempToken = gatewayResponse.headers.get("x-temp-token");

  if (gatewayResponse.status === 403 && detail.detail === "FORCE_PASSWORD_CHANGE" && tempToken) {
    const response = NextResponse.json({ status: "force_password_change" });
    setSessionCookie(response, tempToken);
    return response;
  }

  if (gatewayResponse.status === 403 && detail.detail === "MFA_SETUP_REQUIRED" && tempToken) {
    const response = NextResponse.json({ status: "mfa_setup_required" });
    setSessionCookie(response, tempToken);
    return response;
  }

  if (gatewayResponse.status === 401 && detail.detail === "TOTP_CODE_REQUIRED") {
    return NextResponse.json({ status: "totp_required" });
  }

  return NextResponse.json(
    { status: "error", message: typeof detail.detail === "string" ? detail.detail : "Login failed" },
    { status: gatewayResponse.status }
  );
}
