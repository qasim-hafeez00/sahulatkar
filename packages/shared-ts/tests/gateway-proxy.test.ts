import { describe, expect, it } from "vitest";
import {
  buildForwardableResponseHeaders,
  buildForwardHeaders,
  readForwardableBody,
  type ForwardableRequest,
} from "../src/gateway-proxy";

function mockRequest(overrides: Partial<ForwardableRequest> & { method: string; contentType?: string | null }): ForwardableRequest {
  const headerMap = new Map<string, string>();
  if (overrides.contentType) headerMap.set("content-type", overrides.contentType);

  return {
    method: overrides.method,
    headers: { get: (name: string) => headerMap.get(name.toLowerCase()) ?? null },
    formData: overrides.formData ?? (async () => new FormData()),
    text: overrides.text ?? (async () => ""),
  };
}

describe("readForwardableBody", () => {
  it("returns undefined for GET requests", async () => {
    const request = mockRequest({ method: "GET" });
    expect(await readForwardableBody(request)).toBeUndefined();
  });

  it("returns undefined for HEAD requests", async () => {
    const request = mockRequest({ method: "HEAD" });
    expect(await readForwardableBody(request)).toBeUndefined();
  });

  it("reads multipart bodies via formData()", async () => {
    const form = new FormData();
    form.set("file", "contents");
    const request = mockRequest({ method: "POST", contentType: "multipart/form-data; boundary=x", formData: async () => form });
    expect(await readForwardableBody(request)).toBe(form);
  });

  it("reads non-multipart bodies as text", async () => {
    const request = mockRequest({ method: "POST", contentType: "application/json", text: async () => '{"a":1}' });
    expect(await readForwardableBody(request)).toBe('{"a":1}');
  });

  it("returns undefined for an empty text body", async () => {
    const request = mockRequest({ method: "POST", contentType: "application/json", text: async () => "" });
    expect(await readForwardableBody(request)).toBeUndefined();
  });
});

describe("buildForwardHeaders", () => {
  it("always sets the bearer token", () => {
    const headers = buildForwardHeaders("tok123", null, undefined);
    expect(headers.Authorization).toBe("Bearer tok123");
  });

  it("forwards content-type for non-FormData bodies", () => {
    const headers = buildForwardHeaders("tok123", "application/json", '{"a":1}');
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("omits content-type for FormData bodies so fetch can set its own boundary", () => {
    const form = new FormData();
    const headers = buildForwardHeaders("tok123", "multipart/form-data; boundary=x", form);
    expect(headers["Content-Type"]).toBeUndefined();
  });
});

describe("buildForwardableResponseHeaders", () => {
  it("whitelists content-type and content-disposition only", () => {
    const upstream = {
      headers: new Headers({
        "content-type": "application/pdf",
        "content-disposition": "attachment; filename=x.pdf",
        "x-internal-trace": "should-not-leak",
      }),
    };
    const headers = buildForwardableResponseHeaders(upstream);
    expect(headers.get("content-type")).toBe("application/pdf");
    expect(headers.get("content-disposition")).toBe("attachment; filename=x.pdf");
    expect(headers.get("x-internal-trace")).toBeNull();
  });

  it("omits headers that aren't present upstream", () => {
    const headers = buildForwardableResponseHeaders({ headers: new Headers() });
    expect(headers.get("content-type")).toBeNull();
    expect(headers.get("content-disposition")).toBeNull();
  });
});
