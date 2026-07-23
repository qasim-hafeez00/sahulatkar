import { NextRequest, NextResponse } from "next/server";
import { ADMIN_SESSION_COOKIE, verifyAdminToken } from "@/lib/admin-session";
import { adminModules } from "@/lib/admin-modules";

const PUBLIC_DASHBOARD_ROUTES = ["/dashboard/login", "/dashboard/forbidden"];

/** Longest-prefix match of pathname against known module hrefs, e.g. "/dashboard/orders/42" -> "/dashboard/orders". */
function findModuleForPath(pathname: string) {
  let best: (typeof adminModules)[number] | null = null;
  for (const entry of adminModules) {
    if (pathname === entry.href || pathname.startsWith(entry.href + "/")) {
      if (!best || entry.href.length > best.href.length) {
        best = entry;
      }
    }
  }
  return best;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (!pathname.startsWith("/dashboard")) {
    return NextResponse.next();
  }

  if (PUBLIC_DASHBOARD_ROUTES.some((route) => pathname === route || pathname.startsWith(route + "/"))) {
    return NextResponse.next();
  }

  const token = request.cookies.get(ADMIN_SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.redirect(new URL("/dashboard/login", request.url));
  }

  const session = await verifyAdminToken(token);
  if (!session || session.token_type !== "admin") {
    // Either no valid token, or only a short-lived onboarding (temp) token —
    // neither unlocks real dashboard pages, just the public onboarding routes above.
    const response = NextResponse.redirect(new URL("/dashboard/login", request.url));
    response.cookies.delete(ADMIN_SESSION_COOKIE);
    return response;
  }

  const matchedModule = findModuleForPath(pathname);
  if (matchedModule && !matchedModule.roles.includes(session.role as (typeof matchedModule.roles)[number])) {
    return NextResponse.redirect(new URL("/dashboard/forbidden", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
