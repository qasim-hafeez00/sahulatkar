import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { ADMIN_SESSION_COOKIE, verifyAdminToken } from "@/lib/admin-session";
import { getGatewayBaseUrl } from "@/lib/gateway-config";
import { buildForwardableResponseHeaders, buildForwardHeaders, readForwardableBody } from "sk-shared-ts";

const GATEWAY_BASE_URL = getGatewayBaseUrl();

async function proxy(request: NextRequest, params: { path: string[] }) {
  const token = cookies().get(ADMIN_SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "NOT_AUTHENTICATED" }, { status: 401 });
  }

  const session = await verifyAdminToken(token);
  if (!session) {
    return NextResponse.json({ detail: "SESSION_INVALID_OR_EXPIRED" }, { status: 401 });
  }

  const targetPath = "/" + params.path.join("/");
  const targetUrl = `${GATEWAY_BASE_URL}${targetPath}${request.nextUrl.search}`;

  const contentType = request.headers.get("content-type");
  const body = await readForwardableBody(request);
  const headers = buildForwardHeaders(token, contentType, body);

  const gatewayResponse = await fetch(targetUrl, {
    method: request.method,
    headers,
    body,
    cache: "no-store",
  });

  const responseHeaders = buildForwardableResponseHeaders(gatewayResponse);
  const responseBody = await gatewayResponse.arrayBuffer();
  return new NextResponse(responseBody, { status: gatewayResponse.status, headers: responseHeaders });
}

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params);
}
export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params);
}
export async function PUT(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params);
}
export async function PATCH(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params);
}
export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params);
}
