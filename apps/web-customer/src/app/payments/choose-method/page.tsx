"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useRouter } from "next/navigation"
import { ArrowRight, Check, Lock, Wallet, CreditCard, Landmark, ShieldCheck } from "lucide-react"
import { ordersApi } from "@/lib/orders-api"
import type { PaymentMethod } from "@/lib/payments-api"
import { formatCurrency } from "@/lib/utils"

const PAYMENT_METHODS: { id: PaymentMethod; name: string; description: string; icon: typeof Wallet }[] = [
  { id: "easypaisa", name: "EasyPaisa", description: "Pay via mobile wallet or retail shop", icon: Wallet },
  { id: "jazzcash", name: "JazzCash", description: "Direct payment from JazzCash account", icon: Wallet },
  { id: "safepay", name: "Safepay", description: "Visa, Mastercard, or UnionPay checkout", icon: CreditCard },
  { id: "raast", name: "Raast", description: "Instant bank transfer via Raast", icon: Landmark },
]

export default function ChoosePaymentMethod() {
  const [selectedMethod, setSelectedMethod] = useState<PaymentMethod>("easypaisa")
  const [orderIds, setOrderIds] = useState<number[]>([])
  const [subtotal, setSubtotal] = useState(0)
  const [downPayment, setDownPayment] = useState(0)
  const [loaded, setLoaded] = useState(false)
  const router = useRouter()

  useEffect(() => {
    const raw = sessionStorage.getItem("sk_cart_order_ids")
    if (!raw) {
      router.replace("/cart")
      return
    }
    const ids: number[] = JSON.parse(raw)
    // Order ids must be read from sessionStorage, a browser-only API unavailable during SSR.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOrderIds(ids)
    Promise.all(ids.map((id) => ordersApi.get(id)))
      .then((orders) => {
        setSubtotal(orders.reduce((sum, o) => sum + o.total_amount, 0))
        setDownPayment(orders.reduce((sum, o) => sum + (o.down_payment_amount ?? 0), 0))
        setLoaded(true)
      })
      .catch(() => setLoaded(true))
  }, [router])

  const handleProceed = () => {
    sessionStorage.setItem("sk_selected_payment_method", selectedMethod)
    sessionStorage.setItem("sk_down_payment_amount", String(downPayment))
    router.push("/payments/payment-details")
  }

  if (!loaded) return null

  return (
    <div className="min-h-screen pt-28 pb-16">
      <div className="mx-auto max-w-7xl px-4 py-8 lg:px-8">
        <div className="grid gap-8 lg:grid-cols-[1.5fr_1fr]">
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="space-y-6"
          >
            <div>
              <h1 className="text-4xl font-bold text-theme">Choose Payment Method</h1>
              <p className="mt-2 text-theme-muted">
                Securely complete your combined down payment for {orderIds.length} item(s) using our verified fintech partners.
              </p>
            </div>

            <div className="space-y-3">
              {PAYMENT_METHODS.map((method) => {
                const Icon = method.icon
                const isSelected = selectedMethod === method.id
                return (
                  <div
                    key={method.id}
                    onClick={() => setSelectedMethod(method.id)}
                    className={`cursor-pointer rounded-2xl border-2 p-4 transition-all ${
                      isSelected
                        ? "border-[var(--accent)] bg-[var(--accent)]/5"
                        : "border-[var(--section-border)] bg-[var(--card-bg)] hover:border-[var(--accent)]/40"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--section-bg)]">
                          <Icon className="h-5 w-5 text-theme-muted" />
                        </div>
                        <div>
                          <p className="font-semibold text-theme">{method.name}</p>
                          <p className="text-sm text-theme-muted">{method.description}</p>
                        </div>
                      </div>
                      <div
                        className={`flex h-6 w-6 items-center justify-center rounded-full border-2 ${
                          isSelected ? "border-[var(--accent)] bg-[var(--accent)]" : "border-[var(--section-border)]"
                        }`}
                      >
                        {isSelected && <Check className="h-4 w-4 text-white" />}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>

            <Button onClick={handleProceed} size="xl" className="w-full">
              Proceed to Secure Payment <ArrowRight className="h-4 w-4" />
            </Button>

            <div className="flex items-center justify-center gap-2 text-sm text-theme-muted">
              <Lock className="h-4 w-4" />
              <span>Bank-grade 256-bit SSL encrypted connection</span>
            </div>
          </motion.section>

          <motion.aside
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="h-fit sticky top-24"
          >
            <Card className="border-0">
              <CardContent className="space-y-4 p-6">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-theme-muted">Order Summary</p>
                  <span className="mt-2 inline-block rounded-full bg-[var(--success-bg)] px-3 py-1 text-xs font-semibold text-[var(--success)]">
                    SECURED
                  </span>
                </div>

                <div className="border-t border-[var(--section-border)] pt-4">
                  <p className="text-sm text-theme-muted">{orderIds.length} item(s) &mdash; unified financing</p>
                </div>

                <div className="space-y-2 rounded-2xl bg-[var(--section-bg)] p-4">
                  <div className="flex justify-between">
                    <span className="text-sm text-theme-muted">Total Purchase Value</span>
                    <span className="font-semibold text-theme">{formatCurrency(subtotal)}</span>
                  </div>
                </div>

                <div className="rounded-2xl border border-[var(--accent)]/20 bg-[var(--accent)]/5 p-4">
                  <p className="text-xs font-semibold uppercase tracking-widest text-[var(--accent)]">Due Now</p>
                  <p className="mt-3 text-3xl font-bold text-theme">{formatCurrency(Math.round(downPayment))}</p>
                  <p className="mt-1 text-xs text-theme-muted">Combined down payment for the whole cart</p>
                </div>

                <div className="flex gap-2 rounded-2xl border border-[var(--success)]/20 bg-[var(--success-bg)] p-4">
                  <ShieldCheck className="h-5 w-5 shrink-0 text-[var(--success)]" />
                  <div>
                    <p className="text-sm font-semibold text-theme">Shariah Compliant</p>
                    <p className="text-xs text-theme-muted">This transaction follows ethical Murabaha financing principles with transparent pricing.</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.aside>
        </div>
      </div>
    </div>
  )
}
