"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useRouter } from "next/navigation"
import { Lock, CreditCard, FlaskConical } from "lucide-react"
import { paymentsApi, type PaymentMethod } from "@/lib/payments-api"
import { ApiError } from "@/lib/api-client"
import { formatCurrency } from "@/lib/utils"

export default function PaymentDetails() {
  const [cardNumber, setCardNumber] = useState("")
  const [expiryDate, setExpiryDate] = useState("")
  const [cvc, setCvc] = useState("")
  const [cardholderName, setCardholderName] = useState("")
  const [saveCard, setSaveCard] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState("")
  const [amount, setAmount] = useState(0)
  const [method, setMethod] = useState<PaymentMethod>("easypaisa")
  const [orderId, setOrderId] = useState<number | null>(null)
  const router = useRouter()

  useEffect(() => {
    const orderIdsRaw = sessionStorage.getItem("sk_cart_order_ids")
    const amountRaw = sessionStorage.getItem("sk_down_payment_amount")
    const methodRaw = sessionStorage.getItem("sk_selected_payment_method") as PaymentMethod | null
    if (!orderIdsRaw || !amountRaw || !methodRaw) {
      router.replace("/cart")
      return
    }
    const orderIds: number[] = JSON.parse(orderIdsRaw)
    // These values are read from sessionStorage, a browser-only API unavailable during SSR.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOrderId(orderIds[0])
    setAmount(Number(amountRaw))
    setMethod(methodRaw)
  }, [router])

  const isFormValid = cardNumber.replace(/\s/g, "").length >= 12 && expiryDate.length >= 5 && cvc.length >= 3 && cardholderName.trim().length > 0

  const handleConfirm = async () => {
    if (!orderId || !isFormValid) {
      setError("Please fill in all payment details.")
      return
    }
    setIsSubmitting(true)
    setError("")
    try {
      await paymentsApi.payDownPayment(orderId, method, amount)
      router.push("/payments/processing")
    } catch (err) {
      const message = err instanceof ApiError ? String(err.detail) : "Payment could not be processed. Please try again."
      setError(message)
      setIsSubmitting(false)
    }
  }

  const formatCardNumber = (value: string) => {
    const v = value.replace(/\s+/g, "").replace(/[^0-9]/gi, "")
    const matches = v.match(/\d{4,16}/g)
    const match = (matches && matches[0]) || ""
    const parts = []
    for (let i = 0, len = match.length; i < len; i += 4) {
      parts.push(match.substring(i, i + 4))
    }
    if (parts.length) {
      return parts.join(" ")
    } else {
      return value
    }
  }

  return (
    <div className="min-h-screen pt-28 pb-16">
      <div className="mx-auto max-w-7xl px-4 py-8 lg:px-8">
        <div className="grid gap-8 lg:grid-cols-[1fr_1.2fr]">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="h-fit space-y-8 rounded-3xl bg-[var(--foreground)] p-8 text-[var(--background)]"
          >
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest opacity-70">SahulatKar</p>
              <p className="mt-1 text-xs font-bold uppercase tracking-widest text-[var(--accent)]">Premium</p>
            </div>

            <div className="space-y-3">
              <h2 className="text-3xl font-bold leading-tight">Secure Down Payment</h2>
              <p className="text-sm opacity-70">Complete your down payment with end-to-end Shariah-compliant encryption</p>
            </div>

            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-sm opacity-60">Payment Method</span>
                <span className="text-lg font-semibold capitalize">{method}</span>
              </div>
              <div className="flex justify-between border-t border-[var(--background)]/10 pt-3">
                <span className="text-sm opacity-60">Down Payment Due</span>
                <span className="text-4xl font-bold text-[var(--accent)]">{formatCurrency(Math.round(amount))}</span>
              </div>
            </div>

            <div className="flex gap-2 text-xs opacity-60">
              <Lock className="h-3.5 w-3.5" />
              <span>PCI-DSS Level 1 &middot; 256-bit SSL</span>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
          >
            <Card className="border-0">
              <CardContent className="space-y-6 p-8">
                <div>
                  <h3 className="text-2xl font-bold text-theme">Payment Details</h3>
                  <p className="mt-1 text-sm text-theme-muted">Enter your credit or debit card information.</p>
                </div>

                <div className="flex items-start gap-2 rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)]/5 p-3 text-xs text-[var(--accent)]">
                  <FlaskConical className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>Test payment &mdash; this is a development environment. No real card data is submitted or stored.</span>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="mb-2 block text-xs font-semibold uppercase tracking-widest text-theme-muted">
                      Card Number
                    </label>
                    <div className="relative">
                      <CreditCard className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-theme-muted" />
                      <input
                        type="text"
                        placeholder="0000 0000 0000 0000"
                        value={cardNumber}
                        onChange={(e) => setCardNumber(formatCardNumber(e.target.value))}
                        maxLength={19}
                        className="w-full rounded-xl border border-[var(--section-border)] bg-[var(--card-bg)] py-3 pl-10 pr-4 text-theme placeholder:text-theme-muted focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="mb-2 block text-xs font-semibold uppercase tracking-widest text-theme-muted">
                        Expiry Date
                      </label>
                      <input
                        type="text"
                        placeholder="MM / YY"
                        value={expiryDate}
                        onChange={(e) => setExpiryDate(e.target.value)}
                        maxLength={7}
                        className="w-full rounded-xl border border-[var(--section-border)] bg-[var(--card-bg)] px-4 py-3 text-theme placeholder:text-theme-muted focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20"
                      />
                    </div>
                    <div>
                      <label className="mb-2 block text-xs font-semibold uppercase tracking-widest text-theme-muted">
                        CVC / CVV
                      </label>
                      <input
                        type="text"
                        placeholder="•••"
                        value={cvc}
                        onChange={(e) => setCvc(e.target.value)}
                        maxLength={4}
                        className="w-full rounded-xl border border-[var(--section-border)] bg-[var(--card-bg)] px-4 py-3 text-theme placeholder:text-theme-muted focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-2 block text-xs font-semibold uppercase tracking-widest text-theme-muted">
                      Cardholder Name
                    </label>
                    <input
                      type="text"
                      placeholder="Full name as on card"
                      value={cardholderName}
                      onChange={(e) => setCardholderName(e.target.value)}
                      className="w-full rounded-xl border border-[var(--section-border)] bg-[var(--card-bg)] px-4 py-3 text-theme placeholder:text-theme-muted focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20"
                    />
                  </div>

                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      id="savecard"
                      checked={saveCard}
                      onChange={(e) => setSaveCard(e.target.checked)}
                      className="h-4 w-4 rounded border-[var(--section-border)] accent-[var(--accent)]"
                    />
                    <label htmlFor="savecard" className="text-sm text-theme-muted">
                      Save card for future transactions
                    </label>
                  </div>
                </div>

                {error && (
                  <div className="rounded-xl border border-[var(--danger)]/20 bg-[var(--danger-bg)] p-3 text-sm text-[var(--danger)]">
                    {error}
                  </div>
                )}

                <Button
                  onClick={handleConfirm}
                  disabled={isSubmitting || !isFormValid}
                  size="xl"
                  className="w-full"
                >
                  <Lock className="h-4 w-4" /> {isSubmitting ? "Processing..." : "Confirm Payment"}
                </Button>

                <p className="text-center text-xs text-theme-muted">
                  Your transaction is protected by SahulatKar Finance. We do not store your credit card information on our servers.
                </p>
              </CardContent>
            </Card>
          </motion.div>
        </div>
      </div>
    </div>
  )
}
