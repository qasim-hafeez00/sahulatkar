import { apiFetch } from "@/lib/api-client"

export interface OfferPlan {
  installment_count: number
  profit_rate_pct: number
}

export interface OfferProductVariant {
  option_name: string
  options: Array<{ label: string; value: string; is_available?: boolean }>
}

export interface OrderOffer {
  status: "pending" | "ready" | "declined" | "extraction_failed"
  order_id: number
  product?: {
    id: number
    name: string
    url: string
    price: number
    brand?: string | null
    image_url?: string | null
    availability?: "in_stock" | "out_of_stock" | "limited" | "unknown"
    in_stock?: boolean
    variants?: OfferProductVariant[]
  }
  financing?: {
    cost_price: number
    profit_amount: number
    down_payment_pct: number
    plans: OfferPlan[]
  }
  reason?: string
}

export interface CartItemView {
  cart_item_id: number
  order_id: number
  offer: OrderOffer
}

export interface CartResponse {
  cart_id: number | null
  status: "empty" | "open" | "checked_out" | "abandoned"
  items: CartItemView[]
}

export interface CartCheckoutResult {
  cart_id: number
  order_ids: number[]
  installment_count: number
}

export const cartApi = {
  addItem(productUrl: string) {
    return apiFetch<CartItemView>("/cart/items", {
      method: "POST",
      auth: true,
      body: JSON.stringify({ product_url: productUrl }),
    })
  },

  getCart() {
    return apiFetch<CartResponse>("/cart", { auth: true })
  },

  removeItem(cartItemId: number) {
    return apiFetch<void>(`/cart/items/${cartItemId}`, { method: "DELETE", auth: true })
  },

  checkout(installmentCount: 3 | 4 | 6 | 12) {
    return apiFetch<CartCheckoutResult>("/cart/checkout", {
      method: "POST",
      auth: true,
      body: JSON.stringify({ installment_count: installmentCount }),
    })
  },
}
