// Boot-time config validation for the gateway origin, mirroring the
// `validate_critical_settings` pattern used by apps/gateway/src/config.py and
// apps/product-service/src/config.py: refuse to silently run with an
// insecure/placeholder default outside local development.
//
// All 4 web-admin call sites that talk to the gateway origin directly
// (src/app/api/auth/login/route.ts, src/app/api/auth/logout/route.ts,
// src/app/api/gateway/[...path]/route.ts, src/lib/admin-api-server.ts) should
// resolve their base URL through `getGatewayBaseUrl()` instead of reading
// `process.env.NEXT_PUBLIC_GATEWAY_URL` directly, so a missing env var in
// production fails loudly at startup instead of quietly proxying admin
// traffic to http://localhost:8000.
import { getGatewayBaseUrl as getGatewayBaseUrlFor } from "sk-shared-ts";

export function getGatewayBaseUrl(): string {
  return getGatewayBaseUrlFor({ envVar: "NEXT_PUBLIC_GATEWAY_URL" });
}
