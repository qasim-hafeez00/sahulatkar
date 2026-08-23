// Boot-time config validation for the gateway origin, mirroring the
// `validate_critical_settings` pattern used by apps/gateway/src/config.py and
// apps/product-service/src/config.py.
//
// The browser bundle cannot use a dynamic `process.env[envVar]` lookup, so we
// read the public env directly here. Next.js can inline that value at build
// time, and local development still falls back to the gateway on localhost.

const DEFAULT_LOCAL_FALLBACK = "http://localhost:8000/api/v1"

export function getGatewayBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL
  if (configured) {
    return configured
  }

  if (typeof window === "undefined" && process.env.NODE_ENV === "production") {
    throw new Error(
      "GATEWAY_CONFIG_VALIDATION_FAILED: NEXT_PUBLIC_API_URL is not set. " +
        `Refusing to fall back to ${DEFAULT_LOCAL_FALLBACK} in production.`
    )
  }

  return DEFAULT_LOCAL_FALLBACK
}
