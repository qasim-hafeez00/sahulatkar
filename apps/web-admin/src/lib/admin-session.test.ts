import { beforeAll, describe, expect, it } from "vitest";
import { exportSPKI, generateKeyPair, SignJWT } from "jose";
import type { KeyLike } from "jose";

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

describe("verifyAdminToken", () => {
  it("accepts a valid, correctly-signed token", async () => {
    const { verifyAdminToken } = await import("./admin-session");
    const token = await signToken(
      privateKey,
      { admin_id: 42, role: "super_admin", permissions: ["all_actions"], token_type: "admin" },
      "15m"
    );

    const payload = await verifyAdminToken(token);
    expect(payload).not.toBeNull();
    expect(payload?.admin_id).toBe(42);
    expect(payload?.role).toBe("super_admin");
    expect(payload?.token_type).toBe("admin");
  });

  it("rejects an expired token", async () => {
    const { verifyAdminToken } = await import("./admin-session");
    const token = await signToken(
      privateKey,
      { admin_id: 42, role: "super_admin", permissions: [], token_type: "admin" },
      "-1s"
    );

    const payload = await verifyAdminToken(token);
    expect(payload).toBeNull();
  });

  it("rejects a token signed with the wrong (tampered) key", async () => {
    const { verifyAdminToken } = await import("./admin-session");
    const token = await signToken(
      otherPrivateKey,
      { admin_id: 42, role: "super_admin", permissions: [], token_type: "admin" },
      "15m"
    );

    const payload = await verifyAdminToken(token);
    expect(payload).toBeNull();
  });

  it("rejects a malformed token string", async () => {
    const { verifyAdminToken } = await import("./admin-session");
    const payload = await verifyAdminToken("not.a.jwt");
    expect(payload).toBeNull();
  });

  it("rejects a validly-signed token missing a numeric admin_id", async () => {
    const { verifyAdminToken } = await import("./admin-session");
    const token = await signToken(
      privateKey,
      { role: "super_admin", permissions: [], token_type: "admin" },
      "15m"
    );

    const payload = await verifyAdminToken(token);
    expect(payload).toBeNull();
  });
});
