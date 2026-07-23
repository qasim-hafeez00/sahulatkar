import { apiFetch } from "@/lib/api-client"

export interface NotificationItem {
  id: number
  category: string
  priority: string
  title: string
  body: string
  is_read: boolean
  source_reference: string | null
  created_at: string
}

export interface NotificationListResult {
  items: NotificationItem[]
  unread_count: number
  total: number
}

export const notificationsApi = {
  list(unreadOnly = false) {
    const qs = unreadOnly ? "?unread_only=true" : ""
    return apiFetch<NotificationListResult>(`/notifications${qs}`, { auth: true })
  },

  markRead(id: number) {
    return apiFetch<NotificationItem>(`/notifications/${id}/read`, { method: "POST", auth: true })
  },

  markAllRead() {
    return apiFetch<void>("/notifications/read-all", { method: "POST", auth: true })
  },
}

/** Where a notification's "view" action should take the user, based on category. */
export function notificationTarget(n: NotificationItem): string {
  switch (n.category) {
    case "payment":
      return "/repayment"
    case "delivery":
      return "/payments/order-tracking"
    case "credit":
      return "/repayment"
    case "kyc":
      return "/auth/verification-success"
    default:
      return "/notifications"
  }
}
