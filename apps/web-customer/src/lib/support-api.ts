import { apiFetch } from "@/lib/api-client"

export type TicketCategory =
  | "payment_issue"
  | "delivery_issue"
  | "product_issue"
  | "kyc_query"
  | "fraud_report"
  | "refund_request"
  | "contract_query"
  | "account_issue"
  | "general"

export interface TicketSummary {
  id: number
  ticket_number: string
  category: TicketCategory
  subject: string
  status: string
  order_id: number | null
  loan_id: number | null
  created_at: string
  updated_at: string
}

export interface TicketMessage {
  id: number
  sender_type: string
  sender_id: number | null
  message_text: string
  created_at: string
}

export interface TicketDetail extends TicketSummary {
  messages: TicketMessage[]
}

export const supportApi = {
  create(payload: { category: TicketCategory; subject: string; description: string; order_id?: number; loan_id?: number }) {
    return apiFetch<TicketDetail>("/support/tickets", {
      method: "POST",
      auth: true,
      body: JSON.stringify(payload),
    })
  },

  list(category?: TicketCategory) {
    const qs = category ? `?category=${encodeURIComponent(category)}` : ""
    return apiFetch<TicketSummary[]>(`/support/tickets${qs}`, { auth: true })
  },

  get(ticketId: number) {
    return apiFetch<TicketDetail>(`/support/tickets/${ticketId}`, { auth: true })
  },

  addMessage(ticketId: number, message: string) {
    return apiFetch<TicketMessage>(`/support/tickets/${ticketId}/messages`, {
      method: "POST",
      auth: true,
      body: JSON.stringify({ message }),
    })
  },
}
