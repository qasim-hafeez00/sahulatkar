import { NextRequest, NextResponse } from "next/server";

const ADMIN_TOKEN_COOKIE_NAMES = ["sk-admin-token", "admin_token", "admin-jwt"];

export function middleware(request: NextRequest) {
  if (!request.nextUrl.pathname.startsWith("/dashboard")) {
    return NextResponse.next();
  }

  if (request.nextUrl.pathname === "/dashboard/login") {
    return NextResponse.next();
  }

  const hasAdminToken = ADMIN_TOKEN_COOKIE_NAMES.some((cookieName) => request.cookies.has(cookieName));
  if (hasAdminToken) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/dashboard/login", request.url);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
