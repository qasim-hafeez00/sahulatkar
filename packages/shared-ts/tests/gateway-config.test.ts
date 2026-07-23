import { afterEach, describe, expect, it, vi } from "vitest";
import { getGatewayBaseUrl } from "../src/gateway-config";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getGatewayBaseUrl", () => {
  it("returns the configured URL when set, regardless of environment", () => {
    vi.stubEnv("SOME_GATEWAY_URL", "https://gateway.example.com/api/v1");
    vi.stubEnv("NODE_ENV", "production");
    expect(getGatewayBaseUrl({ envVar: "SOME_GATEWAY_URL" })).toBe("https://gateway.example.com/api/v1");
  });

  it("falls back to the default localhost gateway outside production when unset", () => {
    vi.stubEnv("SOME_GATEWAY_URL", "");
    vi.stubEnv("NODE_ENV", "development");
    expect(getGatewayBaseUrl({ envVar: "SOME_GATEWAY_URL" })).toBe("http://localhost:8000/api/v1");
  });

  it("falls back to the localhost gateway in test when unset", () => {
    vi.stubEnv("SOME_GATEWAY_URL", "");
    vi.stubEnv("NODE_ENV", "test");
    expect(getGatewayBaseUrl({ envVar: "SOME_GATEWAY_URL" })).toBe("http://localhost:8000/api/v1");
  });

  it("uses a custom fallback when provided", () => {
    vi.stubEnv("SOME_GATEWAY_URL", "");
    vi.stubEnv("NODE_ENV", "development");
    expect(getGatewayBaseUrl({ envVar: "SOME_GATEWAY_URL", fallback: "http://localhost:9999/api" })).toBe(
      "http://localhost:9999/api"
    );
  });

  it("throws in production when unset instead of silently using localhost", () => {
    vi.stubEnv("SOME_GATEWAY_URL", "");
    vi.stubEnv("NODE_ENV", "production");
    expect(() => getGatewayBaseUrl({ envVar: "SOME_GATEWAY_URL" })).toThrow(/SOME_GATEWAY_URL/);
  });
});
