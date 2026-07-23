import { apiFetch } from "@/lib/api-client"

export type PaymentProvider = "jazzcash" | "easypaisa" | "safepay" | "raast" | "card"
export type PaymentMethodType = "wallet" | "card" | "bank"

export interface SavedPaymentMethod {
  id: number
  provider: PaymentProvider
  method_type: PaymentMethodType
  masked_pan: string | null
  expiry_month: string | null
  expiry_year: string | null
  is_default: boolean
  created_at: string
}

export const paymentMethodsApi = {
  list() {
    return apiFetch<SavedPaymentMethod[]>("/payments/methods", { auth: true })
  },

  add(payload: { provider: PaymentProvider; method_type: PaymentMethodType; account_identifier: string; expiry_month?: string; expiry_year?: string }) {
    return apiFetch<SavedPaymentMethod>("/payments/methods", {
      method: "POST",
      auth: true,
      body: JSON.stringify(payload),
    })
  },

  remove(methodId: number) {
    return apiFetch<void>(`/payments/methods/${methodId}`, { method: "DELETE", auth: true })
  },

  setDefault(methodId: number) {
    return apiFetch<SavedPaymentMethod>(`/payments/methods/${methodId}/default`, { method: "POST", auth: true })
  },
}
