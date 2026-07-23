"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { useRouter } from "next/navigation"
import { contractsApi, type ContractDisclosure } from "@/lib/contracts-api"
import { ApiError } from "@/lib/api-client"

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
    setItems(orderIds.map((orderId) => ({ orderId, contractId: null, disclosure: null, devOtp: null, signed: false })))
  }, [router])

  useEffect(() => {
    if (!items || items[currentIndex]?.contractId) return
    generateForCurrent()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, currentIndex])

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
        <div className="rounded-[2rem] bg-white shadow-[0_40px_90px_rgba(15,23,42,0.08)] overflow-hidden">
          <div className="bg-[#16223f] px-10 py-10 text-center text-white">
            <span className="inline-flex rounded-full border border-white/20 bg-white/10 px-4 py-2 text-xs uppercase tracking-[0.35em] text-white/80">
              Item {currentIndex + 1} of {items.length} — Step 2: Contract Execution
            </span>
            <h1 className="mt-6 text-5xl font-semibold tracking-tight">Murabaha Sale Contract</h1>
            <p className="mx-auto mt-4 max-w-2xl text-sm leading-7 text-slate-300">
              Review the Shariah-compliant financing terms below — a binding agreement for the sale of this item on a
              cost-plus-profit basis, with 100% of any late fees donated to charity.
            </p>
          </div>

          <div className="px-10 py-8 lg:px-14 lg:py-10">
            <div className="grid gap-6 lg:grid-cols-[1.7fr_1fr]">
              <div className="rounded-[1.75rem] bg-[#f8f4ed] p-6 shadow-sm border border-slate-200">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Order Reference</p>
                    <p className="mt-3 text-xl font-semibold text-slate-900">Order #{current.orderId}</p>
                  </div>
                  <div className="rounded-3xl bg-[#11213c] px-4 py-3 text-sm font-semibold text-white">Shariah Compliant</div>
                </div>

                {disclosure ? (
                  <div className="mt-6 grid gap-4 sm:grid-cols-3">
                    <div className="rounded-[1.25rem] bg-white p-4 shadow-sm border border-slate-200">
                      <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Cost Price</p>
                      <p className="mt-3 text-xl font-semibold text-slate-900">PKR {disclosure.cost_price.toLocaleString()}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.28em] text-slate-500">Asset Acquisition Cost</p>
                    </div>
                    <div className="rounded-[1.25rem] bg-white p-4 shadow-sm border border-slate-200">
                      <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Profit (Halal)</p>
                      <p className="mt-3 text-xl font-semibold text-[#c15e00]">PKR {disclosure.profit_amount.toLocaleString()}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.28em] text-slate-500">{disclosure.profit_rate_pct}% Profit Margin</p>
                    </div>
                    <div className="rounded-[1.25rem] bg-[#11213c] p-4 shadow-sm border border-slate-900 text-white">
                      <p className="text-xs uppercase tracking-[0.3em] text-slate-300">Total Sale Price</p>
                      <p className="mt-3 text-3xl font-semibold">PKR {disclosure.total_sale_price.toLocaleString()}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.28em] text-slate-400">{disclosure.installment_count}-month plan</p>
                    </div>
                  </div>
                ) : (
                  <p className="mt-6 text-sm text-slate-500">Loading contract disclosure...</p>
                )}
              </div>

              <div className="rounded-[1.75rem] bg-[#f8f4ed] p-6 shadow-sm border border-slate-200">
                <h2 className="text-lg font-semibold text-slate-900">Key Terms & Conditions</h2>
                <p className="mt-4 text-sm leading-7 text-slate-700">
                  SahulatKar (the &ldquo;Seller&rdquo;) has purchased this item and sells it to you (the &ldquo;Buyer&rdquo;)
                  at the Total Sale Price disclosed above, payable in equal monthly installments.
                </p>
                <p className="mt-3 text-sm leading-7 text-slate-700">
                  No compound interest is charged. Late payments may incur a fee that is donated 100% to charity —
                  SahulatKar retains none of it.
                </p>
              </div>
            </div>

            <div className="mt-8 rounded-[1.75rem] bg-[#f8f4ed] p-6 shadow-sm border border-green-100">
              <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-green-700">Digital Signature Verification</p>
                  <p className="mt-2 text-sm text-slate-600">Enter the 6-digit code sent to your registered mobile number.</p>
                </div>
                <div className="w-full max-w-xs">
                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    value={otp}
                    onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    placeholder="000000"
                    className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-4 text-center text-2xl font-bold tracking-[0.5em] text-slate-900 focus:border-green-500 focus:ring-2 focus:ring-green-200"
                  />
                  {current.devOtp && (
                    <button
                      type="button"
                      onClick={() => setOtp(current.devOtp!)}
                      className="mt-3 w-full rounded-xl border border-orange-300 bg-orange-50 px-4 py-2 text-xs font-semibold text-orange-700 hover:bg-orange-100"
                    >
                      Dev Mode: tap to autofill code {current.devOtp}
                    </button>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-6 rounded-[1.75rem] bg-white p-6 shadow-sm border border-slate-200">
              <label className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={contractAccepted}
                  onChange={(e) => setContractAccepted(e.target.checked)}
                  className="mt-1 h-5 w-5 rounded-lg border border-slate-300 text-[#11213c] focus:ring-[#11213c]"
                />
                <span className="text-sm text-slate-700">I accept the Murabaha sale contract terms and agree to the payment schedule.</span>
              </label>
            </div>

            {error && (
              <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-600">{error}</div>
            )}

            <div className="mt-8">
              <Button
                onClick={handleSign}
                disabled={!contractAccepted || otp.length !== 6 || isSigning || isGenerating || !current.contractId}
                className="w-full rounded-3xl bg-[#11213c] px-6 py-6 text-white hover:bg-[#101d33] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSigning ? "Confirming and Signing..." : "Confirm and Sign Murabaha"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
