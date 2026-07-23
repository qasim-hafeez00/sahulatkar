import { apiFetch } from "@/lib/api-client"

export type PaymentMethod = "safepay" | "jazzcash" | "easypaisa" | "raast"

export interface DownPaymentResult {
  payment_id: number
  status: string
  transaction_id: string | null
  checkout_url: string | null
}

export interface InstallmentDetail {
  id: number
  number: number
  due_date: string
  amount: number
  status: string
  paid_at: string | null
}

export interface PaymentSchedule {
  loan_id: number
  loan_number: string
  total_amount: number
  installments: InstallmentDetail[]
}

export interface VcnStatus {
  order_id: number
  vcn_status: string
  masked_number?: string
  expiry_month?: string
  expiry_year?: string
  order_status: string
}

export const paymentsApi = {
  payDownPayment(orderId: number, method: PaymentMethod, amountPkr: number) {
    return apiFetch<DownPaymentResult>("/payments/down-payment", {
      method: "POST",
      auth: true,
      body: JSON.stringify({ order_id: orderId, method, amount_pkr: amountPkr }),
    })
  },

  getSchedule(orderId: number) {
    return apiFetch<PaymentSchedule>(`/payments/schedule/${orderId}`, { auth: true })
  },

  payInstallment(installmentId: number, method: PaymentMethod, amountPkr: number) {
    return apiFetch<DownPaymentResult>(`/payments/installment/${installmentId}/pay`, {
      method: "POST",
      auth: true,
      body: JSON.stringify({ method, amount_pkr: amountPkr }),
    })
  },

  issueVcn(orderId: number) {
    return apiFetch<{ status: string; order_id: number }>("/payments/vcn/issue", {
      method: "POST",
      auth: true,
      body: JSON.stringify({ order_id: orderId }),
    })
  },

  getVcnStatus(orderId: number) {
    return apiFetch<VcnStatus>(`/payments/vcn/status/${orderId}`, { auth: true })
  },
}
