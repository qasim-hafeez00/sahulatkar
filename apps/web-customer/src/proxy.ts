import { NextRequest, NextResponse } from "next/server"
import {
  REFRESH_COOKIE,
  SESSION_COOKIE,
  clearSessionCookies,
  refreshAccessToken,
  setAccessCookie,
  verifyCustomerToken,
} from "@/lib/session"

// Full list of routes the old ad hoc per-page `useEffect` guards used to
// protect (grepped for `tokenStorage.getAccessToken()` across src/app before
// this change): /dashboard, /profile, /payment-methods, /support (which
// covers /support/[id] and /support/dispute as sub-paths), /notifications,
// /repayment, and /cart.
// /financing and /payments added: these carry the Wakalah/Murabaha signing
// flow and down-payment/VCN/checkout-agent flow — same session-cookie-only
// exposure as the routes above, just missed in the original grep since they
// don't call tokenStorage.getAccessToken() directly (they rely on the
// gateway proxy's 401 instead), so an unauthenticated visitor got the full
// page shell rendered client-side before failing on the first API call.
const PROTECTED_ROUTES = [
  "/dashboard",
  "/profile",
  "/payment-methods",
  "/support",
  "/notifications",
  "/repayment",
  "/cart",
  "/financing",
  "/payments",
]

function isProtected(pathname: string) {
  return PROTECTED_ROUTES.some((route) => pathname === route || pathname.startsWith(route + "/"))
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl

  if (!isProtected(pathname)) {
    return NextResponse.next()
  }

  const token = request.cookies.get(SESSION_COOKIE)?.value
  if (token) {
    const session = await verifyCustomerToken(token)
    if (session) {
      return NextResponse.next()
    }
  }

  // Access token missing or expired — try a silent refresh via the
  // longer-lived refresh cookie before bouncing to login. Access tokens only
  // live 15 minutes; without this, an idle user with a perfectly valid
  // 24-hour session would get logged out on every short break.
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value
  if (refreshToken) {
    const newAccessToken = await refreshAccessToken(refreshToken)
    if (newAccessToken) {
      const response = NextResponse.next()
      setAccessCookie(response, newAccessToken)
      return response
    }
  }

  const response = NextResponse.redirect(new URL("/auth/login", request.url))
  clearSessionCookies(response)
  return response
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/profile/:path*",
    "/payment-methods/:path*",
    "/support/:path*",
    "/notifications/:path*",
    "/repayment/:path*",
    "/cart/:path*",
    "/financing/:path*",
    "/payments/:path*",
  ],
}