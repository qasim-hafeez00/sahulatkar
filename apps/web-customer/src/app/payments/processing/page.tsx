"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { ArrowRight, ShieldCheck } from "lucide-react"
import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ProgressTimeline, type TimelineStep } from "@/components/ui/progress-timeline"
import { CheckoutAgentProgress } from "@/components/ui/checkout-agent-progress"
import { ordersApi } from "@/lib/orders-api"
import { paymentsApi, type VcnStatus } from "@/lib/payments-api"

export default function ProcessingPayment() {
  const [steps, setSteps] = useState([
    { id: 1, label: "Down Payment Confirmed", status: "pending", substatus: "AWAITING_GATEWAY_CONFIRMATION" },
    { id: 2, label: "Issuing Virtual Purchase Cards", status: "pending", substatus: "ROUTING_GATEWAY_LINK" },
    { id: 3, label: "Merchant Purchase", status: "pending", substatus: "AGENT_RUNNING" },
  ])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [vcnCards, setVcnCards] = useState<VcnStatus[]>([])
  const [purchasingOrderIds, setPurchasingOrderIds] = useState<number[]>([])
  const [agentDoneOrderIds, setAgentDoneOrderIds] = useState<Set<number>>(new Set())
  const router = useRouter()

  useEffect(() => {
    let cancelled = false

    const run = async () => {
      const raw = sessionStorage.getItem("sk_cart_order_ids")
      if (!raw) {
        router.replace("/cart")
        return
      }
      const orderIds: number[] = JSON.parse(raw)

      try {
        // Poll until the down payment (confirmed synchronously in dev, async via a
        // real gateway webhook in production) has advanced every order.
        let orders = await Promise.all(orderIds.map((id) => ordersApi.get(id)))
        let attempts = 0
        while (orders.some((o) => o.status === "contracts_signed") && attempts < 20) {
          await new Promise((r) => setTimeout(r, 1500))
          orders = await Promise.all(orderIds.map((id) => ordersApi.get(id)))
          attempts++
        }
        if (cancelled) return
        setSteps((prev) => prev.map((s) => (s.id === 1 ? { ...s, status: "completed" } : s)))

        await Promise.all(orderIds.map((id) => paymentsApi.issueVcn(id)))

        attempts = 0
        orders = await Promise.all(orderIds.map((id) => ordersApi.get(id)))
        while (orders.some((o) => !["vcn_issued", "purchasing", "purchase_confirmed", "delivery_pending", "in_transit", "delivered", "completed"].includes(o.status)) && attempts < 20) {
          await new Promise((r) => setTimeout(r, 1500))
          orders = await Promise.all(orderIds.map((id) => ordersApi.get(id)))
          attempts++
        }
        if (cancelled) return
        setSteps((prev) => prev.map((s) => (s.id === 2 ? { ...s, status: "completed" } : s)))

        const cards = await Promise.all(
          orderIds.map((id) => paymentsApi.getVcnStatus(id).catch(() => null))
        )
        if (cancelled) return
        setVcnCards(cards.filter((c): c is VcnStatus => c !== null))
        setPurchasingOrderIds(orderIds)
        setLoading(false)
      } catch (err) {
        if (!cancelled) setError("Something went wrong while confirming your payment.")
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [router])

  const timelineSteps: TimelineStep[] = steps.map((s) => ({ key: String(s.id), label: s.label }))
  const activeIndex = steps.filter((s) => s.status === "completed").length

  const handleAgentDone = (orderId: number) => {
    setAgentDoneOrderIds((prev) => {
      const next = new Set(prev).add(orderId)
      if (next.size === purchasingOrderIds.length) {
        setSteps((prevSteps) => prevSteps.map((s) => (s.id === 3 ? { ...s, status: "completed" } : s)))
      }
      return next
    })
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-20">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-xl"
      >
        <Card className="border-0">
          <CardContent className="space-y-8 p-8 sm:p-10">
            <div className="flex items-center justify-between gap-4 border-b border-[var(--section-border)] pb-6">
              <div className="space-y-1.5">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--success-bg)] px-3.5 py-1 text-[10px] font-bold uppercase tracking-widest text-[var(--success)]">
                  <ShieldCheck className="h-3 w-3" /> Secure Payment
                </span>
                <h1 className="text-2xl font-bold text-theme sm:text-3xl">
                  {loading ? "Confirming your payment..." : "Payment confirmed"}
                </h1>
              </div>
            </div>

            <ProgressTimeline steps={timelineSteps} activeIndex={activeIndex} className="flex-wrap gap-y-4" />

            <p className="text-sm leading-relaxed text-theme-muted">
              Please don&apos;t close your browser or refresh this page while we confirm your down payment and
              issue your virtual purchase card.
            </p>

            {error ? (
              <div className="rounded-xl border border-[var(--danger)]/20 bg-[var(--danger-bg)] px-4 py-2.5 text-sm font-medium text-[var(--danger)]">
                {error}
              </div>
            ) : loading ? (
              <div className="inline-flex items-center gap-2 rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)]/5 px-4 py-2.5 text-sm font-medium text-[var(--accent)]">
                <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--accent)]" />
                Working on it&hellip;
              </div>
            ) : (
              <>
                {vcnCards.length > 0 && (
                  <div className="space-y-3">
                    {vcnCards.map((card) => (
                      <div
                        key={card.order_id}
                        className="flex items-center justify-between rounded-xl border border-[var(--section-border)] bg-[var(--section-bg)] px-4 py-3"
                      >
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-theme-muted">
                            Order #{card.order_id} — Virtual Purchase Card
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
                  </div>
                )}
                {purchasingOrderIds.length > 0 && (
                  <div className="space-y-4">
                    {purchasingOrderIds.map((orderId) => (
                      <div
                        key={orderId}
                        className="rounded-xl border border-[var(--section-border)] bg-[var(--section-bg)] px-4 py-3.5"
                      >
                        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-theme-muted">
                          Order #{orderId}
                        </p>
                        <CheckoutAgentProgress orderId={orderId} onDone={() => handleAgentDone(orderId)} />
                      </div>
                    ))}
                  </div>
                )}
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ type: "spring", stiffness: 150 }}
                >
                  <Button onClick={() => router.push("/payments/order-success")} size="xl" className="w-full">
                    View Order Confirmation
                    <ArrowRight className="h-5 w-5" />
                  </Button>
                </motion.div>
              </>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}
