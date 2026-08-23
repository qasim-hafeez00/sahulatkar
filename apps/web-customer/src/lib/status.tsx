import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Clock,
  RefreshCw,
  Truck,
} from "lucide-react"

export type Tone = "progress" | "action" | "transit" | "done" | "issue" | "neutral"

export interface StatusMeta {
  label: string
  tone: Tone
}

export const TONE_STYLES: Record<Tone, { badge: string; icon: React.ElementType }> = {
  progress: { badge: "text-sky-600 dark:text-sky-400 bg-sky-500/10 border-sky-500/20", icon: RefreshCw },
  action: { badge: "text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20", icon: Clock },
  transit: { badge: "text-indigo-600 dark:text-indigo-400 bg-indigo-500/10 border-indigo-500/20", icon: Truck },
  done: { badge: "text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20", icon: CheckCircle2 },
  issue: { badge: "text-red-600 dark:text-red-400 bg-red-500/10 border-red-500/20", icon: AlertTriangle },
  neutral: { badge: "text-gray-600 dark:text-gray-400 bg-gray-500/10 border-gray-500/20", icon: Circle },
}

export function formatStatusLabel(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

// Every status the order pipeline can be in (sk_shared.constants.OrderState) mapped to
// plain-language copy — a status a customer has never heard of before must still read
// as "here's what's happening" rather than falling back to a generic spinner.
const ORDER_STATUS_META: Record<string, StatusMeta> = {
  url_submitted: { label: "Reviewing your link", tone: "progress" },
  url_received: { label: "Reviewing your link", tone: "progress" },
  extracting: { label: "Reviewing your link", tone: "progress" },
  extraction_failed: { label: "Couldn't process this link", tone: "issue" },
  offer_presented: { label: "Offer ready to review", tone: "action" },
  offer_accepted: { label: "Offer accepted", tone: "progress" },
  contracts_pending: { label: "Awaiting your signature", tone: "action" },
  contracts_signed: { label: "Contract signed", tone: "progress" },
  down_payment_pending: { label: "Awaiting down payment", tone: "action" },
  down_payment_received: { label: "Down payment received", tone: "progress" },
  vcn_issued: { label: "Preparing your purchase", tone: "progress" },
  purchasing: { label: "Purchasing your item", tone: "progress" },
  purchase_failed: { label: "Purchase failed", tone: "issue" },
  purchase_confirmed: { label: "Purchase confirmed", tone: "progress" },
  delivery_pending: { label: "Preparing for delivery", tone: "transit" },
  in_transit: { label: "On the way", tone: "transit" },
  delivered: { label: "Delivered", tone: "done" },
  delivery_confirmed: { label: "Delivered", tone: "done" },
  completed: { label: "Completed", tone: "done" },
  cancelled: { label: "Cancelled", tone: "issue" },
  refunded: { label: "Refunded", tone: "issue" },
  returned: { label: "Returned", tone: "issue" },
  disputed: { label: "Under review", tone: "issue" },
}

export function getOrderStatusMeta(rawStatus: string): StatusMeta {
  return ORDER_STATUS_META[rawStatus] ?? { label: formatStatusLabel(rawStatus), tone: "neutral" }
}

export function isDeliveredStatus(status: string): boolean {
  return status === "delivered" || status === "delivery_confirmed" || status === "completed"
}

export function isClosedOrderStatus(status: string): boolean {
  return isDeliveredStatus(status) || ["cancelled", "refunded", "returned", "extraction_failed", "purchase_failed"].includes(status)
}

export function humanizeAccountStatus(status: string | undefined): string {
  if (!status) return "—"
  if (status === "pending_kyc") return "Verification in progress"
  return formatStatusLabel(status)
}

// KYC verification status (sk_shared KycVerification.status).
const KYC_STATUS_META: Record<string, StatusMeta> = {
  pending: { label: "Not started", tone: "neutral" },
  submitted: { label: "Under review", tone: "progress" },
  in_review: { label: "Under review", tone: "progress" },
  approved: { label: "Verified", tone: "done" },
  rejected: { label: "Needs attention", tone: "issue" },
}

export function getKycStatusMeta(status: string | undefined): StatusMeta {
  if (!status) return { label: "Not started", tone: "neutral" }
  return KYC_STATUS_META[status] ?? { label: formatStatusLabel(status), tone: "neutral" }
}

// Support ticket status (apps/gateway support_tickets.status): open, in_progress, waiting_user, resolved, closed.
const TICKET_STATUS_META: Record<string, StatusMeta> = {
  open: { label: "Open — awaiting our team", tone: "action" },
  in_progress: { label: "Being worked on", tone: "progress" },
  waiting_user: { label: "Waiting on your reply", tone: "action" },
  resolved: { label: "Resolved", tone: "done" },
  closed: { label: "Closed", tone: "neutral" },
}

export function getTicketStatusMeta(status: string): StatusMeta {
  return TICKET_STATUS_META[status] ?? { label: formatStatusLabel(status), tone: "neutral" }
}

// Notification category (apps/gateway notifications.category): payment, delivery, credit, kyc, general.
export const NOTIFICATION_CATEGORY_META: Record<string, { label: string; icon: string; tone: Tone }> = {
  payment: { label: "Payment", icon: "payment", tone: "action" },
  delivery: { label: "Delivery", icon: "delivery", tone: "transit" },
  credit: { label: "Credit", icon: "credit", tone: "done" },
  kyc: { label: "Verification", icon: "kyc", tone: "progress" },
  general: { label: "Update", icon: "general", tone: "neutral" },
}

export function getNotificationCategoryMeta(category: string) {
  return NOTIFICATION_CATEGORY_META[category] ?? NOTIFICATION_CATEGORY_META.general
}
