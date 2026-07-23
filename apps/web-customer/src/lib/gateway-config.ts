// Boot-time config validation for the gateway origin, mirroring the
// `validate_critical_settings` pattern used by apps/gateway/src/config.py and
// apps/product-service/src/config.py, and apps/web-admin's own
// src/lib/gateway-config.ts: refuse to silently run with an
// insecure/placeholder default outside local development.
//
// All web-customer call sites that talk to the gateway origin directly
// should resolve their base URL through `getGatewayBaseUrl()` instead of
// reading `process.env.NEXT_PUBLIC_API_URL` directly, so a missing env var
// in production fails loudly at startup instead of quietly proxying
// customer traffic to http://localhost:8000.
import { getGatewayBaseUrl as getGatewayBaseUrlFor } from "sk-shared-ts";

export function getGatewayBaseUrl(): string {
  return getGatewayBaseUrlFor({ envVar: "NEXT_PUBLIC_API_URL" });
}
