// All admin API calls go through the same-origin `/api/gateway/*` proxy
// (see src/app/api/gateway/[...path]/route.ts) rather than the gateway
// origin directly — the proxy attaches the admin's session JWT server-side
// from an httpOnly cookie that client code can never read.
const PROXY_BASE = "/api/gateway";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${PROXY_BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers ?? {}),
    },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || response.statusText);
  }

  const contentType = response.headers.get("content-type");
  if (contentType?.includes("application/json")) {
    return response.json() as Promise<T>;
  }
  return (await response.blob()) as unknown as T;
}

export const adminApi = {
  get: <T>(path: string) => requestJson<T>(path),
  post: <T>(path: string, body?: unknown) =>
    requestJson<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  put: <T>(path: string, body?: unknown) =>
    requestJson<T>(path, {
      method: "PUT",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body?: unknown) =>
    requestJson<T>(path, {
      method: "PATCH",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  delete: <T>(path: string) => requestJson<T>(path, { method: "DELETE" }),
  postForm: <T>(path: string, form: FormData) =>
    requestJson<T>(path, { method: "POST", body: form }),
};
