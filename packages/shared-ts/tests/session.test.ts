import { beforeAll, describe, expect, it } from "vitest";
import { exportSPKI, generateKeyPair, SignJWT } from "jose";
import type { JWTPayload, KeyLike } from "jose";

interface AdminSessionPayload extends JWTPayload {
  admin_id: number;
  role: string;
}

let privateKey: KeyLike;
let otherPrivateKey: KeyLike;

async function signToken(key: KeyLike, claims: Record<string, unknown>, expiresIn: string) {
  return new SignJWT(claims)
    .setProtectedHeader({ alg: "RS256" })
    .setIssuedAt()
    .setExpirationTime(expiresIn)
    .sign(key);
}

beforeAll(async () => {
  const pair = await generateKeyPair("RS256");
  privateKey = pair.privateKey;
  process.env.JWT_PUBLIC_KEY = await exportSPKI(pair.publicKey);

  const otherPair = await generateKeyPair("RS256");
  otherPrivateKey = otherPair.privateKey;
});

describe("verifyGatewaySession", () => {
  it("accepts a valid, correctly-signed token with the required numeric claim", async () => {
    const { verifyGatewaySession } = await import("../src/session");
    const token = await signToken(privateKey, { admin_id: 42, role: "super_admin" }, "15m");

    const payload = await verifyGatewaySession<AdminSessionPayload>(token, "admin_id");
    expect(payload).not.toBeNull();
    expect(payload?.admin_id).toBe(42);
    expect(payload?.role).toBe("super_admin");
  });

  it("rejects an expired token", async () => {
    const { verifyGatewaySession } = await import("../src/session");
    const token = await signToken(privateKey, { admin_id: 42, role: "super_admin" }, "-1s");

    const payload = await verifyGatewaySession<AdminSessionPayload>(token, "admin_id");
    expect(payload).toBeNull();
  });

  it("rejects a token signed with the wrong (tampered) key", async () => {
    const { verifyGatewaySession } = await import("../src/session");
    const token = await signToken(otherPrivateKey, { admin_id: 42, role: "super_admin" }, "15m");

    const payload = await verifyGatewaySession<AdminSessionPayload>(token, "admin_id");
    expect(payload).toBeNull();
  });

  it("rejects a malformed token string", async () => {
    const { verifyGatewaySession } = await import("../src/session");
    const payload = await verifyGatewaySession("not.a.jwt", "admin_id");
    expect(payload).toBeNull();
  });

  it("rejects a validly-signed token missing the required numeric claim", async () => {
    const { verifyGatewaySession } = await import("../src/session");
    const token = await signToken(privateKey, { role: "super_admin" }, "15m");

    const payload = await verifyGatewaySession<AdminSessionPayload>(token, "admin_id");
    expect(payload).toBeNull();
  });

  it("supports a different required claim (e.g. user_id) against the same key", async () => {
    const { verifyGatewaySession } = await import("../src/session");
    const token = await signToken(privateKey, { user_id: 7 }, "15m");

    const payload = await verifyGatewaySession<JWTPayload & { user_id: number }>(token, "user_id");
    expect(payload).not.toBeNull();
    expect(payload?.user_id).toBe(7);
  });
});

describe("maxAgeFromToken", () => {
  it("returns seconds until exp when present", async () => {
    const { maxAgeFromToken } = await import("../src/session");
    const token = await signToken(privateKey, { admin_id: 1 }, "10m");
    const maxAge = maxAgeFromToken(token, 999);
    expect(maxAge).toBeGreaterThan(500);
    expect(maxAge).toBeLessThanOrEqual(600);
  });

  it("floors at 60 seconds for an already-expired token", async () => {
    const { maxAgeFromToken } = await import("../src/session");
    const token = await signToken(privateKey, { admin_id: 1 }, "-1h");
    expect(maxAgeFromToken(token, 999)).toBe(60);
  });

  it("falls back to fallbackSeconds for an unparseable token", async () => {
    const { maxAgeFromToken } = await import("../src/session");
    expect(maxAgeFromToken("not.a.jwt", 123)).toBe(123);
  });
});

describe("gatewayCookieOptions", () => {
  it("marks cookies secure only in production", async () => {
    const { gatewayCookieOptions } = await import("../src/session");
    process.env.NODE_ENV = "development";
    expect(gatewayCookieOptions(60, true)).toEqual({
      httpOnly: true,
      secure: false,
      sameSite: "lax",
      path: "/",
      maxAge: 60,
    });

    process.env.NODE_ENV = "production";
    expect(gatewayCookieOptions(60, false).secure).toBe(true);
    process.env.NODE_ENV = "test";
  });
});
