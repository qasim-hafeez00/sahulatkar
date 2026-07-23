// Shared plumbing for the `/api/gateway/[...path]` reverse-proxy Route
// Handlers in web-admin and web-customer. Typed structurally against the
// subset of the Fetch API's Request/Response used here (rather than
// importing `next/server`) since the two apps run different major versions
// of Next.js.
export interface ForwardableRequest {
  method: string;
  headers: { get(name: string): string | null };
  formData(): Promise<FormData>;
  text(): Promise<string>;
}

/** Materializes the request body once so it can be reused (e.g. retried after a token refresh). */
export async function readForwardableBody(request: ForwardableRequest): Promise<BodyInit | undefined> {
  if (["GET", "HEAD"].includes(request.method)) {
    return undefined;
  }

  const contentType = request.headers.get("content-type");
  if (contentType?.includes("multipart/form-data")) {
    return request.formData();
  }

  const text = await request.text();
  return text || undefined;
}

/** Builds the headers to forward to the gateway: bearer auth + the original content-type (skipped for FormData, which needs fetch to set its own multipart boundary). */
export function buildForwardHeaders(
  token: string,
  contentType: string | null,
  body: BodyInit | undefined
): Record<string, string> {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (contentType && !(body instanceof FormData)) {
    headers["Content-Type"] = contentType;
  }
  return headers;
}

/** Whitelists the response headers worth forwarding back to the browser. */
export function buildForwardableResponseHeaders(gatewayResponse: { headers: { get(name: string): string | null } }): Headers {
  const headers = new Headers();
  const contentType = gatewayResponse.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const disposition = gatewayResponse.headers.get("content-disposition");
  if (disposition) headers.set("content-disposition", disposition);
  return headers;
}
