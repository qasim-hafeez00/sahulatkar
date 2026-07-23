// Server-only session/cookie helpers for gateway-issued RS256 JWTs. Both
// web-admin and web-customer sign/verify their session cookies with the same
// key pair (settings.JWT_PRIVATE_KEY / JWT_PUBLIC_KEY in
// apps/gateway/src/config.py) — only the required numeric claim differs
// (admin_id vs user_id). Edge-safe: jose + fetch only, no Node-only APIs.
import { decodeJwt, importSPKI, jwtVerify, type JWTPayload, type KeyLike } from "jose";

let cachedKey: KeyLike | Uint8Array | null = null;

async function getPublicKey(): Promise<KeyLike | Uint8Array> {
  if (cachedKey) return cachedKey;
  const pem = process.env.JWT_PUBLIC_KEY;
  if (!pem) throw new Error("JWT_PUBLIC_KEY is not configured");
  cachedKey = await importSPKI(pem, "RS256");
  return cachedKey;
}

/**
 * Verifies signature + expiry of a gateway-issued JWT and checks that
 * `requiredField` is present as a number on the payload. Returns null on any
 * signature/expiry/shape failure.
 */
export async function verifyGatewaySession<T extends JWTPayload>(
  token: string,
  requiredField: keyof T & string
): Promise<T | null> {
  try {
    const key = await getPublicKey();
    const { payload } = await jwtVerify(token, key, { algorithms: ["RS256"] });
    if (typeof (payload as Record<string, unknown>)[requiredField] !== "number") {
      return null;
    }
    return payload as T;
  } catch {
    return null;
  }
}

/** Seconds until `token`'s `exp` claim, floored at 60s, or `fallbackSeconds` if it can't be read. */
export function maxAgeFromToken(token: string, fallbackSeconds: number): number {
  try {
    const decoded = decodeJwt(token);
    if (typeof decoded.exp === "number") {
      return Math.max(decoded.exp - Math.floor(Date.now() / 1000), 60);
    }
  } catch {
    // fall through to the default below
  }
  return fallbackSeconds;
}

export interface GatewayCookieOptions {
  httpOnly: boolean;
  secure: boolean;
  sameSite: "lax";
  path: string;
  maxAge: number;
}

export function gatewayCookieOptions(maxAge: number, httpOnly: boolean): GatewayCookieOptions {
  return {
    httpOnly,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge,
  };
}
