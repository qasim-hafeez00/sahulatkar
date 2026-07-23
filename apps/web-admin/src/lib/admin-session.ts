import type { JWTPayload } from "jose";
import { verifyGatewaySession } from "sk-shared-ts";

export const ADMIN_SESSION_COOKIE = "sk_admin_session";

export interface AdminSessionPayload extends JWTPayload {
  admin_id: number;
  role: string;
  permissions: string[];
  token_type: string;
}

/**
 * Verifies signature + expiry of a gateway-issued admin-domain JWT. Accepts
 * both full "admin" sessions and short-lived "temp" tokens (used for the
 * FORCE_PASSWORD_CHANGE / MFA_SETUP_REQUIRED onboarding flows, which have no
 * real session yet) — callers that need to distinguish the two should check
 * `payload.token_type` themselves. Returns null on any signature/expiry failure.
 */
export async function verifyAdminToken(token: string): Promise<AdminSessionPayload | null> {
  return verifyGatewaySession<AdminSessionPayload>(token, "admin_id");
}
