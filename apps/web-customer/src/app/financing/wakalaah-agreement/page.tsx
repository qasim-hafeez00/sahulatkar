"use client"

import { useEffect, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { ShieldCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ProgressTimeline } from "@/components/ui/progress-timeline"
import { OtpInput } from "@/components/ui/otp-input"
import { useRouter } from "next/navigation"
import { contractsApi } from "@/lib/contracts-api"
import { ApiError } from "@/lib/api-client"
import { formatCurrency } from "@/lib/utils"

interface ItemState {
  orderId: number
  contractId: number | null
  authorizedAmount: number | null
  devOtp: string | null
  signed: boolean
}

export default function WakalaahAgreement() {
  const router = useRouter()
  const [items, setItems] = useState<ItemState[] | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [otp, setOtp] = useState("")
  const [isSigning, setIsSigning] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    const raw = sessionStorage.getItem("sk_cart_order_ids")
    if (!raw) {
      router.replace("/cart")
      return
    }
    const orderIds: number[] = JSON.parse(raw)
    // Initial cart state must be read from sessionStorage, a browser-only API unavailable during SSR.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setItems(orderIds.map((orderId) => ({ orderId, contractId: null, authorizedAmount: null, devOtp: null, signed: false })))
  }, [router])

  const generateForCurrent = async () => {
    if (!items) return
    setIsGenerating(true)
    setError("")
    try {
      const result = await contractsApi.generateWakalah(items[currentIndex].orderId)
      setItems((prev) => {
        if (!prev) return prev
        const next = [...prev]
        next[currentIndex] = {
          ...next[currentIndex],
          contractId: result.contract_id,
          authorizedAmount: result.authorized_amount,
          devOtp: result.dev_otp ?? null,
        }
        return next
      })
    } catch (err) {
      setError("Could not generate the Wakalah agreement for this item. Please try again.")
    } finally {
      setIsGenerating(false)
    }
  }

  useEffect(() => {
    if (!items || items[currentIndex]?.contractId) return
    // Generating the agreement requires a network call, which can only happen in an effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    generateForCurrent()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, currentIndex])

  const handleSign = async () => {
    if (!items) return
    const current = items[currentIndex]
    if (!current.contractId || otp.length !== 6) return
    setIsSigning(true)
    setError("")
    try {
      await contractsApi.signWakalah(current.contractId, otp)
      setItems((prev) => {
        if (!prev) return prev
        const next = [...prev]
        next[currentIndex] = { ...next[currentIndex], signed: true }
        return next
      })
      setOtp("")
      if (currentIndex < items.length - 1) {
        setCurrentIndex((i) => i + 1)
      } else {
        router.push("/financing/murabaha-contract")
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
  const timelineSteps = items.map((item) => ({ key: String(item.orderId), label: `Order #${item.orderId}` }))

  return (
    <div className="min-h-screen pt-28 pb-16">
      <div className="mx-auto max-w-7xl px-4 lg:px-8">
        <div className="grid gap-8 xl:grid-cols-[1.65fr_1fr]">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
            <Card className="border-0 overflow-hidden">
              <div className="theme-section rounded-t-2xl px-10 py-8">
                <div className="inline-flex items-center gap-2 rounded-full border border-[var(--section-border)] bg-[var(--card-bg)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-theme-muted">
                  Item {currentIndex + 1} of {items.length}
                </div>
                <div className="mt-8 space-y-4">
                  <p className="text-sm font-semibold uppercase tracking-[0.35em] text-[var(--accent)]">
                    Shariah Compliant Financing
                  </p>
                  <h1 className="text-4xl font-bold tracking-tight text-theme">Wakalah Agency Agreement</h1>
                  <p className="max-w-2xl text-sm text-theme-muted">
                    SahulatKar (the &ldquo;Agent&rdquo;) is hereby authorized to purchase the item below on your behalf
                    (the &ldquo;Principal&rdquo;), for the amount disclosed, before the Murabaha sale contract is issued.
                  </p>
                </div>
              </div>

              <CardContent className="space-y-6 px-10 py-10">
                <div className="rounded-2xl border border-[var(--section-border)] bg-[var(--section-bg)] p-6">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-theme-muted">Order Reference</p>
                      <p className="mt-2 text-lg font-semibold text-theme">Order #{current.orderId}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-theme-muted">Authorized Amount</p>
                      <p className="mt-2 text-xl font-semibold text-theme">
                        {current.authorizedAmount != null ? formatCurrency(current.authorizedAmount) : "Loading..."}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="rounded-2xl bg-[var(--section-bg)] p-6">
                  <p className="text-sm leading-7 text-theme-muted">
                    This appointment is specific to the Murabaha process: SahulatKar purchases the item, takes possession,
                    and only then sells it to you at a disclosed cost-plus-profit price under the separate Murabaha
                    contract you&rsquo;ll sign next.
                  </p>
                </div>

                <div className="rounded-2xl border border-[var(--section-border)] bg-[var(--card-bg)] p-6">
                  <p className="mb-4 text-sm font-semibold text-theme">Enter the 6-digit code sent to your phone</p>
                  <OtpInput value={otp} onChange={setOtp} devOtp={current.devOtp} />
                </div>

                {error && (
                  <div className="rounded-2xl border border-[var(--danger)]/20 bg-[var(--danger-bg)] p-4 text-sm text-[var(--danger)]">
                    {error}
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="space-y-6"
          >
            <Card className="border-0">
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.35em] text-theme-muted">Contract Progress</p>
                    <h2 className="mt-3 text-2xl font-bold text-theme">Wakalah Sign</h2>
                  </div>
                  <div className="rounded-full bg-[var(--section-bg)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] text-theme-muted">
                    Step 1
                  </div>
                </div>

                <ProgressTimeline steps={timelineSteps} activeIndex={currentIndex} className="mt-8 flex-wrap gap-y-4" />

                <div className="mt-8">
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={isSigning ? "signing" : "idle"}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                    >
                      <Button
                        onClick={handleSign}
                        disabled={isSigning || isGenerating || otp.length !== 6 || !current.contractId}
                        size="xl"
                        className="w-full"
                      >
                        {isSigning ? "Signing..." : "Sign Wakalah Agreement"}
                      </Button>
                    </motion.div>
                  </AnimatePresence>
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 bg-[var(--section-bg)]">
              <CardContent className="p-6">
                <div className="flex items-center gap-3 text-theme">
                  <ShieldCheck className="h-5 w-5 text-[var(--success)]" />
                  <span className="font-semibold">Encrypted Session</span>
                </div>
                <p className="mt-3 text-sm text-theme-muted">
                  Your digital signature is legally binding under the Electronic Transactions Ordinance, 2002.
                </p>
              </CardContent>
            </Card>
          </motion.div>
        </div>
      </div>
    </div>
  )
}
