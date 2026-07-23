import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { ADMIN_SESSION_COOKIE } from "@/lib/admin-session";
import { getGatewayBaseUrl } from "@/lib/gateway-config";

const GATEWAY_BASE_URL = getGatewayBaseUrl();

export async function POST() {
  const token = cookies().get(ADMIN_SESSION_COOKIE)?.value;

  if (token) {
    await fetch(`${GATEWAY_BASE_URL}/admin/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    }).catch(() => {});
  }

  const response = NextResponse.json({ status: "ok" });
  response.cookies.delete(ADMIN_SESSION_COOKIE);
  return response;
}
