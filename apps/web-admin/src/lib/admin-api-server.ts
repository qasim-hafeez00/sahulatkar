// Server Component-only gateway client. Unlike lib/api-client.ts (used by
// client components via the same-origin /api/gateway proxy, since browser JS
// can't read the httpOnly session cookie), Server Components run on the
// server already — they can read the cookie directly via next/headers and
// call the gateway origin directly, with no proxy hop needed.
import { cookies } from "next/headers";
import { ADMIN_SESSION_COOKIE } from "@/lib/admin-session";
import { getGatewayBaseUrl } from "@/lib/gateway-config";

const GATEWAY_BASE_URL = getGatewayBaseUrl();

/**
 * Thrown by `adminApiServer` when the gateway responds with a non-2xx
 * status. Carries the HTTP status so callers can distinguish an expected
 * "not found" (404) from a genuine failure (5xx, network error, auth
 * failure) instead of collapsing every failure into the same silent
 * "record not found" UI.
 */
export class GatewayRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "GatewayRequestError";
    this.status = status;
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const token = cookies().get(ADMIN_SESSION_COOKIE)?.value;

  const response = await fetch(`${GATEWAY_BASE_URL}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const message = await response.text();
    throw new GatewayRequestError(message || response.statusText, response.status);
  }

  return response.json() as Promise<T>;
}

export const adminApiServer = {
  get: <T>(path: string) => requestJson<T>(path),
  post: <T>(path: string, body?: unknown) =>
    requestJson<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
};
