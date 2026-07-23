import { beforeAll, describe, expect, it } from "vitest";
import { exportSPKI, generateKeyPair, SignJWT } from "jose";
import type { KeyLike } from "jose";
import { NextRequest } from "next/server";
import { ADMIN_SESSION_COOKIE } from "@/lib/admin-session";

let privateKey: KeyLike;

async function signToken(claims: Record<string, unknown>, expiresIn = "15m") {
  return new SignJWT(claims)
    .setProtectedHeader({ alg: "RS256" })
    .setIssuedAt()
    .setExpirationTime(expiresIn)
    .sign(privateKey);
}

function requestFor(path: string, token?: string) {
  const req = new NextRequest(new URL(path, "https://admin.sahulatkar.pk"));
  if (token) {
    req.cookies.set(ADMIN_SESSION_COOKIE, token);
  }
  return req;
}

beforeAll(async () => {
  const pair = await generateKeyPair("RS256");
  privateKey = pair.privateKey;
  process.env.JWT_PUBLIC_KEY = await exportSPKI(pair.publicKey);
});

describe("admin dashboard middleware", () => {
  it("lets non-dashboard routes through untouched", async () => {
    const { middleware } = await import("./middleware");
    const res = await middleware(requestFor("/api/health"));
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
  });

  it("lets public dashboard routes through without a session", async () => {
    const { middleware } = await import("./middleware");
    const res = await middleware(requestFor("/dashboard/login"));
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
  });

  it("redirects to login when no session cookie is present", async () => {
    const { middleware } = await import("./middleware");
    const res = await middleware(requestFor("/dashboard/orders"));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/dashboard/login");
  });

  it("redirects to login and clears the cookie for an invalid session token", async () => {
    const { middleware } = await import("./middleware");
    const res = await middleware(requestFor("/dashboard/orders", "not-a-real-token"));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/dashboard/login");
    const setCookie = res.headers.get("set-cookie") ?? "";
    expect(setCookie).toContain(ADMIN_SESSION_COOKIE);
  });

  it("redirects to login for a temp (non-admin) token_type", async () => {
    const { middleware } = await import("./middleware");
    const token = await signToken({ admin_id: 1, role: "super_admin", token_type: "temp_force_password_change" });
    const res = await middleware(requestFor("/dashboard/orders", token));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/dashboard/login");
  });

  it("redirects to forbidden when the admin's role lacks access to the module", async () => {
    const { middleware } = await import("./middleware");
    // /dashboard/admins (AD-25 "Team & Access") is super_admin only.
    const token = await signToken({ admin_id: 7, role: "cs_agent", token_type: "admin" });
    const res = await middleware(requestFor("/dashboard/admins", token));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/dashboard/forbidden");
  });

  it("allows access when the admin's role matches the module", async () => {
    const { middleware } = await import("./middleware");
    const token = await signToken({ admin_id: 7, role: "super_admin", token_type: "admin" });
    const res = await middleware(requestFor("/dashboard/admins", token));
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
  });

  it("allows access to a path nested under a role-matched module", async () => {
    const { middleware } = await import("./middleware");
    const token = await signToken({ admin_id: 7, role: "cs_agent", token_type: "admin" });
    const res = await middleware(requestFor("/dashboard/orders/42", token));
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
  });
});
