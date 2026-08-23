"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useRouter } from "next/navigation"
import { contractsApi, type ContractDisclosure } from "@/lib/contracts-api"
import { ApiError } from "@/lib/api-client"
import { formatCurrency } from "@/lib/utils"
import { OtpInput } from "@/components/ui/otp-input"

interface ItemState {
  orderId: number
  contractId: number | null
  disclosure: ContractDisclosure | null
  devOtp: string | null
  signed: boolean
}

export default function MurabahaContract() {
  const router = useRouter()
  const [items, setItems] = useState<ItemState[] | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [otp, setOtp] = useState("")
  const [contractAccepted, setContractAccepted] = useState(false)
  const [isSigning, setIsSigning] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    const raw = sessionStorage.getItem("sk_cart_order_ids")
    const installmentCountRaw = sessionStorage.getItem("sk_cart_installment_count")
    if (!raw || !installmentCountRaw) {
      router.replace("/cart")
      return
    }
    const orderIds: number[] = JSON.parse(raw)
    // Initial cart state must be read from sessionStorage, a browser-only API unavailable during SSR.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setItems(orderIds.map((orderId) => ({ orderId, contractId: null, disclosure: null, devOtp: null, signed: false })))
  }, [router])

  const generateForCurrent = async () => {
    if (!items) return
    const installmentCount = Number(sessionStorage.getItem("sk_cart_installment_count") ?? "4") as 3 | 4 | 6 | 12
    setIsGenerating(true)
    setError("")
    try {
      const result = await contractsApi.generateMurabaha(items[currentIndex].orderId, installmentCount)
      setItems((prev) => {
        if (!prev) return prev
        const next = [...prev]
        next[currentIndex] = {
          ...next[currentIndex],
          contractId: result.contract_id,
          disclosure: result.disclosure,
          devOtp: result.dev_otp ?? null,
        }
        return next
      })
    } catch (err) {
      const message = err instanceof ApiError ? String(err.detail) : "Could not generate the Murabaha contract for this item."
      setError(message)
    } finally {
      setIsGenerating(false)
    }
  }

  useEffect(() => {
    if (!items || items[currentIndex]?.contractId) return
    // Generating the contract requires a network call, which can only happen in an effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    generateForCurrent()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, currentIndex])

  const handleSign = async () => {
    if (!items || !contractAccepted) return
    const current = items[currentIndex]
    if (!current.contractId || otp.length !== 6) return
    setIsSigning(true)
    setError("")
    try {
      await contractsApi.signMurabaha(current.contractId, otp)
      setItems((prev) => {
        if (!prev) return prev
        const next = [...prev]
        next[currentIndex] = { ...next[currentIndex], signed: true }
        return next
      })
      setOtp("")
      setContractAccepted(false)
      if (currentIndex < items.length - 1) {
        setCurrentIndex((i) => i + 1)
      } else {
        router.push("/payments/choose-method")
      }
    } catch (err) {
      const message = err instanceof ApiError ? String(err.detail) : "Invalid or expired code. Please try again."
      setError(message)
    } finally {
      setIsSigning(false)
    }
  }

  if (!items) return null

  const current = items[currentIndex]
  const disclosure = current.disclosure

  return (
    <div className="min-h-screen pt-28 pb-16">
      <div className="mx-auto max-w-6xl px-4 lg:px-8">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
          <Card className="border-0 overflow-hidden">
            <div className="theme-section rounded-t-2xl px-10 py-10 text-center">
              <span className="inline-flex rounded-full border border-[var(--section-border)] bg-[var(--card-bg)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.35em] text-theme-muted">
                Item {currentIndex + 1} of {items.length} &mdash; Step 2: Contract Execution
              </span>
              <h1 className="mt-6 text-4xl font-bold tracking-tight text-theme sm:text-5xl">Murabaha Sale Contract</h1>
              <p className="mx-auto mt-4 max-w-2xl text-sm leading-7 text-theme-muted">
                Review the Shariah-compliant financing terms below &mdash; a binding agreement for the sale of this item on a
                cost-plus-profit basis, with 100% of any late fees donated to charity.
              </p>
            </div>

            <CardContent className="px-10 py-8 lg:px-14 lg:py-10">
              <div className="grid gap-6 lg:grid-cols-[1.7fr_1fr]">
                <div className="rounded-2xl border border-[var(--section-border)] bg-[var(--section-bg)] p-6">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.35em] text-theme-muted">Order Reference</p>
                      <p className="mt-3 text-xl font-semibold text-theme">Order #{current.orderId}</p>
                    </div>
                    <div className="rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white">
                      Shariah Compliant
                    </div>
                  </div>

                  {disclosure ? (
                    <div className="mt-6 grid gap-4 sm:grid-cols-3">
                      <div className="rounded-xl border border-[var(--section-border)] bg-[var(--card-bg)] p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-theme-muted">Cost Price</p>
                        <p className="mt-3 text-xl font-semibold text-theme">{formatCurrency(disclosure.cost_price)}</p>
                        <p className="mt-1 text-xs uppercase tracking-[0.28em] text-theme-muted">Asset Acquisition Cost</p>
                      </div>
                      <div className="rounded-xl border border-[var(--section-border)] bg-[var(--card-bg)] p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-theme-muted">Profit (Halal)</p>
                        <p className="mt-3 text-xl font-semibold text-[var(--accent)]">{formatCurrency(disclosure.profit_amount)}</p>
                        <p className="mt-1 text-xs uppercase tracking-[0.28em] text-theme-muted">{disclosure.profit_rate_pct}% Profit Margin</p>
                      </div>
                      <div className="rounded-xl bg-[var(--foreground)] p-4 text-[var(--background)]">
                        <p className="text-xs font-semibold uppercase tracking-[0.3em] opacity-70">Total Sale Price</p>
                        <div className="mt-3 flex items-baseline gap-2">
                          <span className="text-2xl font-bold">
                            {formatCurrency(Math.round(disclosure.total_sale_price / disclosure.installment_count))}
                          </span>
                          <span className="text-sm opacity-70">/mo</span>
                        </div>
                        <p className="mt-1 text-xs uppercase tracking-[0.28em] opacity-70">
                          {formatCurrency(disclosure.total_sale_price)} total &middot; {disclosure.installment_count}-month plan
                        </p>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-6 text-sm text-theme-muted">Loading contract disclosure...</p>
                  )}
                </div>

                <div className="rounded-2xl border border-[var(--section-border)] bg-[var(--section-bg)] p-6">
                  <h2 className="text-lg font-semibold text-theme">Key Terms &amp; Conditions</h2>
                  <p className="mt-4 text-sm leading-7 text-theme-muted">
                    SahulatKar (the &ldquo;Seller&rdquo;) has purchased this item and sells it to you (the &ldquo;Buyer&rdquo;)
                    at the Total Sale Price disclosed above, payable in equal monthly installments.
                  </p>
                  <p className="mt-3 text-sm leading-7 text-theme-muted">
                    No compound interest is charged. Late payments may incur a fee that is donated 100% to charity &mdash;
                    SahulatKar retains none of it.
                  </p>
                </div>
              </div>

              <div className="mt-8 rounded-2xl border border-[var(--success)]/20 bg-[var(--success-bg)] p-6">
                <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.35em] text-[var(--success)]">Digital Signature Verification</p>
                    <p className="mt-2 text-sm text-theme-muted">Enter the 6-digit code sent to your registered mobile number.</p>
                  </div>
                  <div className="w-full max-w-xs">
                    <OtpInput value={otp} onChange={setOtp} devOtp={current.devOtp} />
                  </div>
                </div>
              </div>

              <div className="mt-6 rounded-2xl border border-[var(--section-border)] bg-[var(--card-bg)] p-6">
                <label className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={contractAccepted}
                    onChange={(e) => setContractAccepted(e.target.checked)}
                    className="mt-1 h-5 w-5 rounded-lg border border-[var(--section-border)] text-[var(--accent)] focus:ring-[var(--accent)]"
                  />
                  <span className="text-sm text-theme-muted">I accept the Murabaha sale contract terms and agree to the payment schedule.</span>
                </label>
              </div>

              {error && (
                <div className="mt-6 rounded-2xl border border-[var(--danger)]/20 bg-[var(--danger-bg)] p-4 text-sm text-[var(--danger)]">
                  {error}
                </div>
              )}

              <div className="mt-8">
                <Button
                  onClick={handleSign}
                  disabled={!contractAccepted || otp.length !== 6 || isSigning || isGenerating || !current.contractId}
                  size="xl"
                  className="w-full"
                >
                  {isSigning ? "Confirming and Signing..." : "Confirm and Sign Murabaha"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  )
}
