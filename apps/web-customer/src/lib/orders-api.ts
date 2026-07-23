import { apiFetch } from "@/lib/api-client"

export interface OrderSummary {
  id: number
  status: string
  total_amount: number
  down_payment_amount: number | null
  installment_count: number | null
  created_at: string
}

export interface OrderDetail extends OrderSummary {
  product_id: number | null
  product_description: string | null
}

export interface TrackingEvent {
  event_code: string
  event_description: string
  location_city: string | null
  event_time: string
}

export interface OrderTracking {
  order_id: number
  order_status: string
  shipment: {
    tracking_number: string
    courier: string
    status: string
    estimated_delivery: string | null
    last_event: TrackingEvent | null
  } | null
  message?: string
}

export const ordersApi = {
  list(statusFilter?: string) {
    const qs = statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : ""
    return apiFetch<OrderSummary[]>(`/orders${qs}`, { auth: true })
  },

  get(orderId: number) {
    return apiFetch<OrderDetail>(`/orders/${orderId}`, { auth: true })
  },

  getOffer(orderId: number) {
    return apiFetch<import("@/lib/cart-api").OrderOffer>(`/orders/${orderId}/offer`, { auth: true })
  },

  tracking(orderId: number) {
    return apiFetch<OrderTracking>(`/orders/${orderId}/tracking`, { auth: true })
  },

  cancel(orderId: number) {
    return apiFetch<{ order_id: number; status: string }>(`/orders/${orderId}/cancel`, {
      method: "POST",
      auth: true,
    })
  },
}
