import { NextRequest, NextResponse } from "next/server"
import { SESSION_COOKIE } from "@/lib/session"
import { getGatewayBaseUrl } from "@/lib/gateway-config"

// Dedicated streaming proxy for the checkout-agent live-status SSE endpoint.
// The generic /api/gateway/[...path] proxy (route.ts one level up) buffers
// the entire upstream response via `arrayBuffer()` before replying, which
// cannot work for a long-lived Server-Sent Events stream — this route
// instead pipes the gateway's ReadableStream body straight through to the
// browser as it arrives.
export async function GET(request: NextRequest, { params }: { params: Promise<{ orderId: string }> }) {
  const { orderId } = await params
  const token = request.cookies.get(SESSION_COOKIE)?.value
  if (!token) {
    return NextResponse.json({ detail: "NOT_AUTHENTICATED" }, { status: 401 })
  }

  const gatewayResponse = await fetch(`${getGatewayBaseUrl()}/orders/${orderId}/agent-status`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  })

  if (!gatewayResponse.ok || !gatewayResponse.body) {
    const detail = await gatewayResponse.text().catch(() => "AGENT_STATUS_UNAVAILABLE")
    return NextResponse.json({ detail }, { status: gatewayResponse.status || 502 })
  }

  return new NextResponse(gatewayResponse.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  })
}
