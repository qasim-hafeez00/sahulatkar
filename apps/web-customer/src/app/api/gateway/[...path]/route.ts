import { NextRequest, NextResponse } from "next/server"
import {
  REFRESH_COOKIE,
  SESSION_COOKIE,
  clearSessionCookies,
  refreshAccessToken,
  setAccessCookie,
} from "@/lib/session"
import { getGatewayBaseUrl } from "@/lib/gateway-config"
import { buildForwardableResponseHeaders, buildForwardHeaders, readForwardableBody } from "sk-shared-ts"

// All authenticated web-customer API calls (see the `auth: true` option in
// src/lib/api-client.ts) go through this same-origin proxy instead of
// hitting the gateway directly from the browser — the proxy attaches the
// session JWT server-side from an httpOnly cookie that client-side JS can
// never read or tamper with. Mirrors apps/web-admin's
// src/app/api/gateway/[...path]/route.ts, plus one addition: on a 401 it
// transparently retries once after refreshing the access token via the
// (also httpOnly) refresh cookie — reproducing the silent refresh-on-401
// behavior that used to live client-side in api-client.ts's
// `refreshAccessToken()`, now impossible client-side since JS can't read
// either token anymore.
const GATEWAY_BASE_URL = getGatewayBaseUrl()

async function callGateway(
  request: NextRequest,
  targetPath: string,
  token: string,
  body: BodyInit | undefined,
  contentType: string | null
) {
  const targetUrl = `${GATEWAY_BASE_URL}${targetPath}${request.nextUrl.search}`
  const headers = buildForwardHeaders(token, contentType, body)

  return fetch(targetUrl, {
    method: request.method,
    headers,
    body,
    cache: "no-store",
  })
}

async function proxy(request: NextRequest, params: { path: string[] }) {
  const token = request.cookies.get(SESSION_COOKIE)?.value
  if (!token) {
    return NextResponse.json({ detail: "NOT_AUTHENTICATED" }, { status: 401 })
  }

  const targetPath = "/" + params.path.join("/")
  const contentType = request.headers.get("content-type")

  // Read the body once up front (as a materialized value, not a stream) so it
  // can be reused if we need to retry the call after a token refresh below.
  const body = await readForwardableBody(request)

  let gatewayResponse = await callGateway(request, targetPath, token, body, contentType)
  let refreshedAccessToken: string | null = null

  if (gatewayResponse.status === 401) {
    const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value
    if (refreshToken) {
      refreshedAccessToken = await refreshAccessToken(refreshToken)
      if (refreshedAccessToken) {
        gatewayResponse = await callGateway(request, targetPath, refreshedAccessToken, body, contentType)
      }
    }
  }

  const responseHeaders = buildForwardableResponseHeaders(gatewayResponse)
  const responseBody = await gatewayResponse.arrayBuffer()
  const response = new NextResponse(responseBody, { status: gatewayResponse.status, headers: responseHeaders })

  if (refreshedAccessToken) {
    setAccessCookie(response, refreshedAccessToken)
  } else if (gatewayResponse.status === 401) {
    // Refresh failed too (or there was no refresh cookie) — the session is
    // truly dead, so drop it rather than leaving stale cookies around.
    clearSessionCookies(response)
  }

  return response
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, await params)
}
export async function POST(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, await params)
}
export async function PUT(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, await params)
}
export async function PATCH(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, await params)
}
export async function DELETE(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, await params)
}
