"use client"

import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { AlertCircle, ArrowLeft, ShieldAlert } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ApiError } from "@/lib/api-client"
import { ordersApi, type OrderSummary } from "@/lib/orders-api"
import { supportApi, type TicketCategory, type TicketSummary } from "@/lib/support-api"

const DISPUTE_CATEGORIES: { id: TicketCategory; label: string }[] = [
  { id: "refund_request", label: "Refund Request" },
  { id: "delivery_issue", label: "Delivery Issue" },
  { id: "payment_issue", label: "Payment Issue" },
  { id: "fraud_report", label: "Report Fraud / Unauthorized Activity" },
]

export default function DisputePage() {
  const router = useRouter()
  const [orders, setOrders] = useState<OrderSummary[]>([])
  const [tickets, setTickets] = useState<TicketSummary[]>([])
  const [orderId, setOrderId] = useState<number | "">("")
  const [category, setCategory] = useState<TicketCategory>("refund_request")
  const [description, setDescription] = useState("")
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const loadTickets = () =>
    Promise.all([
      supportApi.list("refund_request"),
      supportApi.list("delivery_issue"),
      supportApi.list("payment_issue"),
      supportApi.list("fraud_report"),
    ]).then((lists) => {
      const merged = lists.flat().sort((a, b) => b.created_at.localeCompare(a.created_at))
      setTickets(merged)
      return merged
    })

  useEffect(() => {
    // Auth is enforced server-side by middleware.ts before this page ever renders.
    Promise.all([ordersApi.list(), loadTickets()]).then(([o]) => setOrders(o)).finally(() => setLoaded(true))
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setSuccess("")
    setIsSubmitting(true)
    try {
      const selectedOrder = orders.find((o) => o.id === orderId)
      const ticket = await supportApi.create({
        category,
        subject: selectedOrder ? `${DISPUTE_CATEGORIES.find((c) => c.id === category)?.label} — Order #${selectedOrder.id}` : DISPUTE_CATEGORIES.find((c) => c.id === category)?.label ?? "Dispute",
        description,
        order_id: orderId === "" ? undefined : orderId,
      })
      setSuccess(`Request ${ticket.ticket_number} submitted. Track its status below.`)
      setDescription("")
      setOrderId("")
      loadTickets()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not submit your request. Please try again.")
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!loaded) return null

  return (
    <div className="min-h-screen pt-28 pb-16">
      <div className="container mx-auto max-w-4xl px-4">
        <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.6 }} className="mb-8">
          <button onClick={() => router.push("/support")} className="flex items-center gap-1 text-sm text-gray-500 hover:text-orange-500 mb-3">
            <ArrowLeft className="w-4 h-4" /> Back to Help & Support
          </button>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <ShieldAlert className="w-7 h-7 text-orange-500" /> Dispute & Refunds
          </h1>
          <p className="text-gray-600 dark:text-gray-400">Request a refund or report an issue with an order</p>
        </motion.div>

        <Card className="border-0 shadow-large mb-8">
          <CardContent className="p-6">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">Issue Type</label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value as TicketCategory)}
                    className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4 text-sm"
                  >
                    {DISPUTE_CATEGORIES.map((opt) => (
                      <option key={opt.id} value={opt.id}>{opt.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">Related Order (optional)</label>
                  <select
                    value={orderId}
                    onChange={(e) => setOrderId(e.target.value ? Number(e.target.value) : "")}
                    className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4 text-sm"
                  >
                    <option value="">No specific order</option>
                    {orders.map((o) => (
                      <option key={o.id} value={o.id}>Order #{o.id} — PKR {o.total_amount.toLocaleString()}</option>
                    ))}
                  </select>
                </div>
              </div>

              <textarea
                placeholder="Describe what happened..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={5}
                className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4 text-sm resize-none"
                required
              />

              {error && (
                <div className="flex items-center gap-2 text-sm text-red-600">
                  <AlertCircle className="w-4 h-4" /> {error}
                </div>
              )}
              {success && <div className="text-sm text-emerald-600 font-medium">{success}</div>}

              <Button
                type="submit"
                disabled={isSubmitting || !description}
                className="w-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 disabled:opacity-60"
              >
                {isSubmitting ? "Submitting..." : "Submit Request"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Your Requests</h2>
        {tickets.length === 0 ? (
          <p className="text-sm text-gray-500">No dispute or refund requests yet.</p>
        ) : (
          <div className="space-y-2">
            {tickets.map((t) => (
              <button
                key={t.id}
                onClick={() => router.push(`/support/${t.id}`)}
                className="w-full text-left p-4 rounded-xl border border-gray-200 dark:border-white/10 hover:border-orange-500/30 transition-colors flex items-center justify-between"
              >
                <div>
                  <p className="font-semibold text-sm text-gray-900 dark:text-white">{t.subject}</p>
                  <p className="text-xs text-gray-500">{t.ticket_number} • {new Date(t.created_at).toLocaleDateString()}</p>
                </div>
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-orange-500/10 text-orange-600 capitalize">
                  {t.status.replace("_", " ")}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
