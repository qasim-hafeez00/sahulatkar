// Boot-time config validation for a gateway origin env var, mirroring the
// `validate_critical_settings` pattern used by apps/gateway/src/config.py and
// apps/product-service/src/config.py: refuse to silently run with an
// insecure/placeholder default outside local development.
const DEFAULT_LOCAL_FALLBACK = "http://localhost:8000/api/v1";

export interface GatewayConfigOptions {
  /** Name of the env var that holds the gateway base URL (e.g. "NEXT_PUBLIC_GATEWAY_URL"). */
  envVar: string;
  /** Local-dev fallback used when the env var is unset outside production. */
  fallback?: string;
}

export function getGatewayBaseUrl(options: GatewayConfigOptions): string {
  const { envVar, fallback = DEFAULT_LOCAL_FALLBACK } = options;
  const configured = process.env[envVar];
  if (configured) {
    return configured;
  }

  if (process.env.NODE_ENV === "production") {
    throw new Error(
      `GATEWAY_CONFIG_VALIDATION_FAILED: ${envVar} is not set. ` +
        `Refusing to fall back to ${fallback} in production.`
    );
  }

  return fallback;
}
