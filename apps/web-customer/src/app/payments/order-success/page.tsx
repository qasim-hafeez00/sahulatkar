"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { motion } from "framer-motion"
import { Check, ArrowRight, PackageCheck } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { ordersApi, type OrderDetail } from "@/lib/orders-api"
import { paymentsApi, type PaymentSchedule, type VcnStatus } from "@/lib/payments-api"
import { formatCurrency } from "@/lib/utils"

export default function OrderSuccess() {
  const [orders, setOrders] = useState<OrderDetail[]>([])
  const [schedule, setSchedule] = useState<PaymentSchedule | null>(null)
  const [vcnCards, setVcnCards] = useState<VcnStatus[]>([])
  const router = useRouter()

  useEffect(() => {
    const raw = sessionStorage.getItem("sk_cart_order_ids")
    if (!raw) return
    const orderIds: number[] = JSON.parse(raw)
    Promise.all(orderIds.map((id) => ordersApi.get(id))).then(setOrders).catch(() => {})
    if (orderIds[0]) {
      paymentsApi.getSchedule(orderIds[0]).then(setSchedule).catch(() => {})
    }
    Promise.all(orderIds.map((id) => paymentsApi.getVcnStatus(id).catch(() => null))).then((cards) =>
      setVcnCards(cards.filter((c): c is VcnStatus => c !== null))
    )
  }, [])

  const totalAmount = orders.reduce((sum, o) => sum + o.total_amount, 0)
  const nextInstallment = schedule?.installments.find((i) => i.status === "pending")

  return (
    <div className="min-h-screen pt-24 pb-16">
      <div className="mx-auto max-w-3xl px-4 py-12 lg:px-8">
        <div className="mb-8 flex justify-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-[var(--success)]/20 bg-[var(--success-bg)] px-4 py-2">
            <span className="h-2 w-2 rounded-full bg-[var(--success)]" />
            <span className="text-xs font-semibold uppercase tracking-wider text-[var(--success)]">Verified</span>
          </div>
        </div>

        <div className="mb-12 space-y-6 text-center">
          <motion.div
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", stiffness: 200, damping: 15 }}
          >
            <div className="mx-auto flex h-24 w-24 items-center justify-center rounded-full bg-[var(--success-bg)]">
              <Check className="h-12 w-12 text-[var(--success)]" strokeWidth={3} />
            </div>
          </motion.div>

          <h1 className="text-4xl font-bold text-theme">Order Placed Successfully</h1>
          <p className="text-lg text-theme-muted">Your {orders.length}-item purchase has been financed and confirmed.</p>
        </div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.15 }}>
          <Card className="mb-8 border-0 overflow-hidden">
            <div className="border-b border-[var(--section-border)] bg-[var(--section-bg)] px-8 py-6">
              <p className="text-xs font-semibold uppercase tracking-widest text-theme-muted">Orders</p>
              <p className="mt-2 font-mono text-2xl font-bold text-theme">
                {orders.map((o) => `#${o.id}`).join(", ") || "Loading..."}
              </p>
            </div>

            <CardContent className="space-y-6 p-8">
              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-4">
                  {orders.map((order) => (
                    <div key={order.id} className="flex items-start gap-4">
                      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[var(--section-bg)]">
                        <PackageCheck className="h-5 w-5 text-[var(--accent)]" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold uppercase tracking-wider text-theme-muted">Order #{order.id}</p>
                        <p className="text-lg font-bold text-theme">{formatCurrency(order.total_amount)}</p>
                        <p className="text-sm capitalize text-theme-muted">{order.status.replace(/_/g, " ")}</p>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="space-y-4 rounded-2xl bg-[var(--foreground)] p-6 text-[var(--background)]">
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wider opacity-60">Combined Financing Plan</p>
                    {schedule ? (
                      <div className="flex items-baseline gap-2">
                        <span className="text-3xl font-bold">{formatCurrency(Math.round(schedule.installments[0]?.amount ?? 0))}</span>
                        <span className="text-sm opacity-60">/mo</span>
                      </div>
                    ) : (
                      <p className="text-sm opacity-60">Loading schedule...</p>
                    )}
                  </div>

                  <div className="space-y-2 border-t border-[var(--background)]/10 pt-4">
                    <div className="flex justify-between text-sm">
                      <span className="opacity-60">Total Purchase Value</span>
                      <span className="font-semibold">{formatCurrency(totalAmount)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="opacity-60">Installments</span>
                      <span className="font-semibold">{schedule?.installments.length ?? "—"} months</span>
                    </div>
                  </div>

                  {nextInstallment && (
                    <p className="pt-2 text-xs opacity-60">
                      Next installment due {new Date(nextInstallment.due_date).toLocaleDateString()}.
                    </p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {vcnCards.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="mb-8 space-y-3"
          >
            <p className="text-xs font-semibold uppercase tracking-widest text-theme-muted">
              Virtual Purchase Cards
            </p>
            {vcnCards.map((card) => (
              <div
                key={card.order_id}
                className="flex items-center justify-between rounded-xl border border-[var(--section-border)] bg-[var(--section-bg)] px-4 py-3"
              >
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-theme-muted">
                    Order #{card.order_id}
                  </p>
                  <p className="mt-1 font-mono text-sm font-bold text-theme">
                    {card.masked_number ?? "Issued"}
                    {card.expiry_month && card.expiry_year ? ` · ${card.expiry_month}/${card.expiry_year}` : ""}
                  </p>
                </div>
                <span className="rounded-full bg-[var(--success-bg)] px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-[var(--success)]">
                  {card.vcn_status}
                </span>
              </div>
            ))}
          </motion.div>
        )}

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.25 }}
          className="mb-8 grid gap-4 md:grid-cols-2"
        >
          <Button variant="secondary" size="xl" onClick={() => router.push("/dashboard")}>
            Continue to Dashboard
          </Button>
          <Button size="xl" onClick={() => router.push("/payments/order-tracking")}>
            Track Shariah Order
            <ArrowRight className="h-4 w-4" />
          </Button>
        </motion.div>
      </div>
    </div>
  )
}
