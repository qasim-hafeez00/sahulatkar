"use client"

import { useEffect, useState } from "react"
import { CheckCircle, Clock, ShieldCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useRouter } from "next/navigation"
import { contractsApi } from "@/lib/contracts-api"
import { ApiError } from "@/lib/api-client"

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
    setItems(orderIds.map((orderId) => ({ orderId, contractId: null, authorizedAmount: null, devOtp: null, signed: false })))
  }, [router])

  useEffect(() => {
    if (!items || items[currentIndex]?.contractId) return
    generateForCurrent()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, currentIndex])

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

  return (
    <div className="min-h-screen pt-28 pb-16">
      <div className="mx-auto max-w-7xl px-4 lg:px-8">
        <div className="grid gap-8 xl:grid-cols-[1.65fr_1fr]">
          <section className="overflow-hidden rounded-[2rem] bg-white shadow-[0_40px_90px_rgba(15,23,42,0.08)]">
            <div className="bg-[#16223f] px-10 py-8 text-white">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-xs uppercase tracking-[0.3em] text-white/80">
                Item {currentIndex + 1} of {items.length}
              </div>
              <div className="mt-8 space-y-4">
                <p className="text-sm uppercase tracking-[0.35em] text-slate-300">Shariah Compliant Financing</p>
                <h1 className="text-4xl font-semibold tracking-tight text-white">Wakalah Agency Agreement</h1>
                <p className="max-w-2xl text-sm text-slate-300">
                  SahulatKar (the &ldquo;Agent&rdquo;) is hereby authorized to purchase the item below on your behalf
                  (the &ldquo;Principal&rdquo;), for the amount disclosed, before the Murabaha sale contract is issued.
                </p>
              </div>
            </div>

            <div className="space-y-6 px-10 py-10">
              <div className="rounded-[1.5rem] border border-slate-200 bg-[#fffdf8] p-6 shadow-sm">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Order Reference</p>
                    <p className="mt-2 text-lg font-semibold text-slate-900">Order #{current.orderId}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Authorized Amount</p>
                    <p className="mt-2 text-xl font-semibold text-slate-900">
                      {current.authorizedAmount != null ? `PKR ${current.authorizedAmount.toLocaleString()}` : "Loading..."}
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-[1.5rem] bg-[#f8f4ed] p-6 shadow-sm ring-1 ring-slate-200/70">
                <p className="text-sm leading-7 text-slate-700">
                  This appointment is specific to the Murabaha process: SahulatKar purchases the item, takes possession,
                  and only then sells it to you at a disclosed cost-plus-profit price under the separate Murabaha
                  contract you&rsquo;ll sign next.
                </p>
              </div>

              <div className="rounded-[1.5rem] border border-slate-200 bg-[#fffdf8] p-6 shadow-sm">
                <p className="mb-4 text-sm font-semibold text-slate-900">Enter the 6-digit code sent to your phone</p>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="000000"
                  className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-4 text-center text-2xl font-bold tracking-[0.5em] text-slate-900 focus:border-orange-500 focus:ring-2 focus:ring-orange-200"
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

              {error && (
                <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-600">{error}</div>
              )}
            </div>
          </section>

          <aside className="space-y-6">
            <div className="rounded-[2rem] bg-white p-6 shadow-[0_30px_70px_rgba(15,23,42,0.08)] border border-slate-200">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Contract Progress</p>
                  <h2 className="mt-3 text-2xl font-semibold text-slate-900">Wakalah Sign</h2>
                </div>
                <div className="rounded-full bg-slate-100 px-3 py-1 text-xs uppercase tracking-[0.3em] text-slate-600">Step 1</div>
              </div>

              <div className="mt-6 space-y-3">
                {items.map((item, index) => (
                  <div key={item.orderId} className="flex items-center justify-between rounded-2xl bg-slate-50 p-4">
                    <div className="flex items-center gap-3">
                      <div className={`flex h-9 w-9 items-center justify-center rounded-2xl ${item.signed ? "bg-emerald-100 text-emerald-700" : index === currentIndex ? "bg-orange-100 text-orange-600" : "bg-slate-100 text-slate-500"}`}>
                        {item.signed ? <CheckCircle className="w-4 h-4" /> : <Clock className="w-4 h-4" />}
                      </div>
                      <p className="text-sm font-semibold text-slate-900">Order #{item.orderId}</p>
                    </div>
                    <span className={`text-sm ${item.signed ? "text-emerald-700" : "text-slate-500"}`}>
                      {item.signed ? "Signed" : index === currentIndex ? "In progress" : "Pending"}
                    </span>
                  </div>
                ))}
              </div>

              <div className="mt-6">
                <Button
                  onClick={handleSign}
                  disabled={isSigning || isGenerating || otp.length !== 6 || !current.contractId}
                  className="w-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white py-6 rounded-2xl font-semibold disabled:opacity-50"
                >
                  {isSigning ? "Signing..." : "Sign Wakalah Agreement"}
                </Button>
              </div>
            </div>

            <div className="rounded-[2rem] bg-[#f8f4ed] p-6 shadow-sm border border-slate-200">
              <div className="flex items-center gap-3 text-slate-900">
                <ShieldCheck className="w-5 h-5 text-emerald-700" />
                <span className="font-semibold">Encrypted Session</span>
              </div>
              <p className="mt-3 text-sm text-slate-600">
                Your digital signature is legally binding under the Electronic Transactions Ordinance, 2002.
              </p>
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}
