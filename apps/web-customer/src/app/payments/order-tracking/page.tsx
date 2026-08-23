"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Check, Shield, Truck, HelpCircle } from "lucide-react"
import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ordersApi, type OrderTracking as OrderTrackingData } from "@/lib/orders-api"

const STATUS_STEPS = [
  { code: "contracts_signed", title: "Contract Signed" },
  { code: "down_payment_received", title: "Down Payment Confirmed" },
  { code: "vcn_issued", title: "Virtual Card Issued" },
  { code: "purchase_confirmed", title: "Merchant Purchase Confirmed" },
  { code: "delivery_pending", title: "Shipment Dispatched" },
  { code: "delivered", title: "Delivered" },
]

const TERMINAL_STATUSES = new Set(["delivered", "completed", "cancelled", "refunded"])
const TRACKING_POLL_MS = 15000

export default function OrderTracking() {
  const router = useRouter()
  const [orderIds, setOrderIds] = useState<number[]>([])
  const [tracking, setTracking] = useState<OrderTrackingData | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    const raw = sessionStorage.getItem("sk_cart_order_ids")
    if (!raw) {
      // Order ids are read from sessionStorage, a browser-only API unavailable during SSR.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLoaded(true)
      return
    }
    const ids: number[] = JSON.parse(raw)
    setOrderIds(ids)
    if (!ids[0]) {
      setLoaded(true)
      return
    }

    let cancelled = false
    let timer: number | null = null

    const poll = () => {
      ordersApi
        .tracking(ids[0])
        .then((data) => {
          if (cancelled) return
          setTracking(data)
          setLoaded(true)
          if (!TERMINAL_STATUSES.has(data.order_status)) {
            timer = window.setTimeout(poll, TRACKING_POLL_MS)
          }
        })
        .catch(() => {
          if (!cancelled) setLoaded(true)
        })
    }
    poll()

    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [])

  if (!loaded) return null

  const currentStepIndex = tracking ? STATUS_STEPS.findIndex((s) => s.code === tracking.order_status) : -1

  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto px-4 max-w-7xl">
        <div className="flex items-center justify-between mb-8 border-b border-[var(--section-border)] pb-4">
          <div className="flex items-center gap-2">
            <span className="text-sm font-black text-theme uppercase tracking-wider">SahulatKar</span>
            <span className="text-[10px] bg-orange-500/10 border border-orange-500/20 px-2.5 py-0.5 rounded-full text-orange-500 font-bold uppercase font-mono">
              Delivery Secure
            </span>
          </div>
          <div className="flex items-center gap-4 text-xs font-mono text-theme-muted tracking-wider">
            <span>Tracking ID:</span>
            <span className="text-orange-500 font-bold uppercase">{tracking?.shipment?.tracking_number ?? `ORDER-${orderIds[0] ?? "—"}`}</span>
          </div>
        </div>

        <div className="grid gap-8 lg:grid-cols-12 items-stretch">
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="lg:col-span-8 space-y-8"
          >
            <Card className="card-surface">
              <CardContent className="p-6 sm:p-8">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
                  <div>
                    <h3 className="text-xl font-bold text-theme">Order #{orderIds[0] ?? "—"} Progress</h3>
                    <p className="text-xs text-theme-muted mt-1">Real-time order status from the SahulatKar ledger</p>
                  </div>
                  <div className="inline-flex items-center gap-2 bg-orange-500/10 border border-orange-500/20 rounded-xl px-4 py-2.5">
                    <Truck className="w-4 h-4 text-orange-500 animate-pulse" />
                    <span className="text-xs font-mono font-black text-orange-500 uppercase">
                      {tracking?.shipment?.status?.replace(/_/g, " ") ?? tracking?.order_status.replace(/_/g, " ") ?? "Loading"}
                    </span>
                  </div>
                </div>

                <div className="relative pl-6 border-l border-[var(--section-border)] space-y-8 ml-3 text-left">
                  {STATUS_STEPS.map((step, idx) => {
                    const isCompleted = currentStepIndex >= 0 && idx < currentStepIndex
                    const isActive = idx === currentStepIndex
                    return (
                      <div key={step.code} className="relative group">
                        <div className={`absolute -left-[35px] top-1.5 w-5 h-5 rounded-full flex items-center justify-center border-4 border-[var(--card-bg)] ${
                          isCompleted
                            ? "bg-emerald-500 shadow-md shadow-emerald-500/10"
                            : isActive
                            ? "bg-orange-500 shadow-md shadow-orange-500/10 animate-pulse"
                            : "bg-[var(--section-bg)]"
                        }`}>
                          {isCompleted && <Check className="w-2.5 h-2.5 text-white" />}
                        </div>
                        <div className="space-y-1 pl-2">
                          <h4 className={`text-sm font-bold ${isActive ? "text-orange-500" : isCompleted ? "text-theme" : "text-theme-muted"}`}>
                            {step.title}
                          </h4>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </CardContent>
            </Card>

            {tracking?.shipment?.last_event && (
              <Card className="card-surface">
                <CardContent className="p-6">
                  <div className="flex items-center justify-between mb-4 border-b border-[var(--section-border)] pb-3">
                    <div className="flex items-center space-x-2">
                      <div className="w-2.5 h-2.5 rounded-full bg-orange-500 animate-ping" />
                      <h3 className="text-sm font-extrabold text-theme uppercase tracking-wider">Latest Tracking Event</h3>
                    </div>
                  </div>
                  <div className="bg-slate-950 border border-white/5 rounded-xl p-4 font-mono text-[11px] leading-relaxed text-emerald-400 text-left">
                    <p>❯ {tracking.shipment.last_event.event_description}</p>
                    <p className="text-gray-500 mt-1">
                      {tracking.shipment.last_event.location_city} — {new Date(tracking.shipment.last_event.event_time).toLocaleString()}
                    </p>
                  </div>
                </CardContent>
              </Card>
            )}
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.15 }}
            className="lg:col-span-4 space-y-8"
          >
            <Card className="card-surface p-6 h-full flex flex-col justify-between relative overflow-hidden bg-gradient-to-br from-slate-900 via-slate-950 to-orange-950/20 text-white border-slate-800">
              <div className="absolute top-0 right-0 w-24 h-24 bg-orange-500/5 rounded-full blur-2xl pointer-events-none" />

              <div className="space-y-6">
                <div className="border-b border-white/5 pb-4">
                  <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">Shipment</span>
                  <h4 className="text-base font-bold text-slate-200 mt-1">{tracking?.shipment?.courier ?? "Awaiting dispatch"}</h4>
                  {tracking?.shipment?.estimated_delivery && (
                    <p className="text-[10px] text-orange-400 font-mono tracking-wider mt-0.5">
                      ETA {new Date(tracking.shipment.estimated_delivery).toLocaleDateString()}
                    </p>
                  )}
                </div>

                <div className="space-y-4 pt-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-400">Items in this cart:</span>
                    <span className="font-bold text-slate-250">{orderIds.length}</span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-400">Order Status:</span>
                    <span className="font-extrabold text-slate-200 font-mono capitalize">{tracking?.order_status.replace(/_/g, " ") ?? "—"}</span>
                  </div>
                </div>

                <div className="p-4 bg-orange-500/10 border border-orange-500/20 rounded-2xl flex items-start gap-2.5 text-left">
                  <Shield className="w-5 h-5 text-orange-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <h5 className="text-[10px] font-bold tracking-wider text-orange-300 uppercase">Secure Delivery</h5>
                    <p className="text-[10px] text-gray-400 leading-relaxed mt-0.5">
                      A verification code will be required upon arrival.
                    </p>
                  </div>
                </div>
              </div>

              <div className="space-y-3 pt-6 border-t border-white/5 mt-6">
                <Button
                  onClick={() => router.push("/dashboard")}
                  className="w-full rounded-xl bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white font-bold h-11 shadow-md shadow-orange-500/10 btn-smooth"
                >
                  Return to Dashboard
                </Button>
                <Button
                  variant="outline"
                  className="w-full h-11 rounded-xl font-bold border-white/10 dark:hover:bg-white/5 hover:border-orange-500/30 text-white flex items-center justify-center gap-1.5"
                >
                  <HelpCircle className="w-4 h-4 text-gray-400" />
                  Support Desk
                </Button>
              </div>
            </Card>
          </motion.div>
        </div>
      </div>
    </div>
  )
}
