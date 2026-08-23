// Client for the checkout-agent live-status stream. Unlike every other API
// module here, this does NOT go through api-client.ts's apiFetch (which is
// request/response, not a stream) — it opens an EventSource against the
// dedicated /api/agent-status/[orderId] streaming proxy (see route.ts next
// to it), which re-streams Gateway's SSE response, which in turn re-streams
// Product Service's execution status stream.

export const AGENT_STEP_LABELS: Record<string, string> = {
  queued: "Queued for purchase",
  navigating: "Navigating to merchant",
  variant_selection: "Selecting product variant",
  add_to_cart: "Adding to cart",
  price_drift_check: "Verifying price hasn't changed",
  guest_checkout: "Starting guest checkout",
  form_fill: "Filling shipping details",
  shipping_selection: "Selecting shipping method",
  payment_injection: "Entering payment details",
  review_order_page: "Reviewing order",
  order_submitted: "Submitting order",
  order_confirmed: "Order confirmed",
  pending_verification: "Verifying payment with merchant",
  receipt_captured: "Capturing receipt",
  checkout_uncertain: "Needs manual review",
}

export const AGENT_STEP_ORDER = [
  "queued",
  "navigating",
  "variant_selection",
  "add_to_cart",
  "price_drift_check",
  "guest_checkout",
  "form_fill",
  "shipping_selection",
  "payment_injection",
  "review_order_page",
  "order_submitted",
  "order_confirmed",
  "pending_verification",
  "receipt_captured",
]

export interface AgentStatusEvent {
  step?: string
  status?: string
  timestamp?: string
  done?: boolean
  error?: string
}

/**
 * Opens an SSE connection for one order's checkout-agent execution.
 * Returns an unsubscribe function. Silently no-ops on `AGENT_JOB_NOT_STARTED`
 * (404) since the agent may not have been queued yet — callers should retry
 * by re-invoking this after a short delay if they need eventual coverage.
 */
export function watchAgentStatus(
  orderId: number,
  onEvent: (event: AgentStatusEvent) => void,
  onError?: () => void
): () => void {
  const source = new EventSource(`/api/agent-status/${orderId}`)

  source.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data))
    } catch {
      // ignore malformed frames
    }
  }
  source.onerror = () => {
    source.close()
    onError?.()
  }

  return () => source.close()
}
