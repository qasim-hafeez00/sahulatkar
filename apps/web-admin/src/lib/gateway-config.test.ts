import { afterEach, describe, expect, it, vi } from "vitest";
import { getGatewayBaseUrl } from "./gateway-config";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getGatewayBaseUrl", () => {
  it("returns the configured URL when set, regardless of environment", () => {
    vi.stubEnv("NEXT_PUBLIC_GATEWAY_URL", "https://gateway.example.com/api/v1");
    vi.stubEnv("NODE_ENV", "production");
    expect(getGatewayBaseUrl()).toBe("https://gateway.example.com/api/v1");
  });

  it("falls back to the localhost gateway outside production when unset", () => {
    vi.stubEnv("NEXT_PUBLIC_GATEWAY_URL", "");
    vi.stubEnv("NODE_ENV", "development");
    expect(getGatewayBaseUrl()).toBe("http://localhost:8000/api/v1");
  });

  it("falls back to the localhost gateway in test when unset", () => {
    vi.stubEnv("NEXT_PUBLIC_GATEWAY_URL", "");
    vi.stubEnv("NODE_ENV", "test");
    expect(getGatewayBaseUrl()).toBe("http://localhost:8000/api/v1");
  });

  it("throws in production when unset instead of silently using localhost", () => {
    vi.stubEnv("NEXT_PUBLIC_GATEWAY_URL", "");
    vi.stubEnv("NODE_ENV", "production");
    expect(() => getGatewayBaseUrl()).toThrow(/NEXT_PUBLIC_GATEWAY_URL/);
  });
});
