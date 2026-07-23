"use client"

import { useRouter } from "next/navigation"
import { authApi } from "@/lib/auth-api"

// The AuthGuard component that used to live in this file (a client-side
// `useEffect` redirect wrapper) was never actually rendered anywhere in the
// app — it was dead code. Route protection is now handled by
// src/middleware.ts, which verifies the httpOnly session cookie server-side
// before a protected page's HTML is even sent to the browser, so a
// client-side "flash of protected content then redirect" guard is not
// needed as a replacement. It has been removed rather than wired in.
//
// useAuth() itself is still used (Header, Profile) purely for its logout()
// helper, so it stays.
export function useAuth() {
  const router = useRouter()

  const logout = async () => {
    await authApi.logout()
    router.push('/auth/login')
  }

  return { logout }
}
