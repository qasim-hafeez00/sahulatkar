import { ApiError } from "sk-shared-ts"
import { getGatewayBaseUrl } from "@/lib/gateway-config"

// Authenticated calls are proxied through this same-origin route (see
// src/app/api/gateway/[...path]/route.ts) instead of hitting the gateway
// directly — the proxy attaches the session JWT server-side from an
// httpOnly cookie that client-side JS can never read or tamper with.
// Unauthenticated calls (register, login, OTP verify, forgot/reset
// password) still go straight to the gateway, same as before.
const PROXY_BASE = "/api/gateway"

export { ApiError }

interface RequestOptions extends RequestInit {
  /** Route this call through the authenticated same-origin proxy instead of hitting the gateway directly. */
  auth?: boolean
}

function resolveApiBaseUrl(): string {
  return getGatewayBaseUrl()
}

/**
 * Cheap client-side "is there probably a session" check for UI purposes only
 * (e.g. Header showing Sign In vs. Log Out) — reads the non-httpOnly
 * sk_auth_state hint cookie set by the login/verify-otp Route Handlers. This
 * is never authoritative: middleware.ts and the /api/gateway proxy always
 * re-verify the real httpOnly session cookie server-side before granting
 * access to anything, regardless of what this returns.
 */
export function hasClientSession(): boolean {
  if (typeof document === "undefined") return false
  return document.cookie.split("; ").some((entry) => entry === "sk_auth_state=1")
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { auth = false, headers, ...rest } = options
  const base = auth ? PROXY_BASE : resolveApiBaseUrl()

  const mergedHeaders: Record<string, string> = {
    // Let the browser set multipart/form-data (with boundary) itself for FormData bodies.
    ...(rest.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(headers as Record<string, string> | undefined),
  }

  const response = await fetch(`${base}${path}`, {
    ...rest,
    headers: mergedHeaders,
    // Same-origin requests already carry cookies by default, but this makes
    // the intent explicit: the httpOnly session cookie rides along automatically.
    credentials: "same-origin",
  })

  if (response.status === 204) {
    return undefined as T
  }

  const isJson = response.headers.get("content-type")?.includes("application/json")
  const body = isJson ? await response.json().catch(() => null) : null

  if (!response.ok) {
    throw new ApiError(response.status, body?.detail ?? body ?? response.statusText)
  }

  return body as T
}
