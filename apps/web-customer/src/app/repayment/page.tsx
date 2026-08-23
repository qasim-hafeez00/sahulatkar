"use client"

import { motion } from "framer-motion"
import { useEffect, useMemo, useState } from "react"
import { CreditCard, Smartphone, CheckCircle2, AlertCircle, AlertTriangle, ArrowRight, Banknote, Calendar, Wallet, TrendingUp, CalendarClock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ordersApi } from "@/lib/orders-api"
import { paymentsApi, type InstallmentDetail, type PaymentMethod } from "@/lib/payments-api"
import { ApiError } from "@/lib/api-client"
import { formatCurrency } from "@/lib/utils"

interface ScheduleWithLoan {
  loanId: number
  loanNumber: string
  installments: InstallmentDetail[]
}

interface InstallmentWithLoan extends InstallmentDetail {
  loanNumber: string
  daysLeft: number
}

const METHODS: { id: PaymentMethod; name: string; description: string; icon: typeof Banknote; color: string }[] = [
  { id: "raast", name: "Raast Instant Payment", description: "Instant bank transfer via Pakistan's real-time payment system", icon: Banknote, color: "from-green-500 to-green-600" },
  { id: "easypaisa", name: "EasyPaisa", description: "Pay using your EasyPaisa mobile wallet", icon: Smartphone, color: "from-green-600 to-green-700" },
  { id: "jazzcash", name: "JazzCash", description: "Pay using your JazzCash mobile wallet", icon: Smartphone, color: "from-blue-500 to-blue-600" },
  { id: "safepay", name: "Card via Safepay", description: "Visa, Mastercard, or UnionPay", icon: CreditCard, color: "from-purple-500 to-purple-600" },
]

function RepaymentsSkeleton() {
  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto px-4 max-w-6xl animate-pulse">
        <div className="card-surface h-10 w-52 rounded-xl mb-3" />
        <div className="card-surface h-5 w-80 rounded-lg mb-8" />
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {[0, 1, 2, 3].map((i) => <div key={i} className="card-surface h-28 rounded-2xl" />)}
        </div>
        <div className="card-surface h-80 rounded-2xl" />
      </div>
    </div>
  )
}

export default function Repayments() {
  const [schedules, setSchedules] = useState<ScheduleWithLoan[]>([])
  const [selectedInstallment, setSelectedInstallment] = useState<InstallmentWithLoan | null>(null)
  const [selectedMethod, setSelectedMethod] = useState<PaymentMethod | "">("")
  const [isPaying, setIsPaying] = useState(false)
  const [error, setError] = useState("")
  const [loaded, setLoaded] = useState(false)

  const loadSchedules = async () => {
    try {
      const orders = await ordersApi.list()
      const seen = new Set<number>()
      const results: ScheduleWithLoan[] = []
      for (const order of orders) {
        try {
          const schedule = await paymentsApi.getSchedule(order.id)
          if (!seen.has(schedule.loan_id)) {
            seen.add(schedule.loan_id)
            results.push({ loanId: schedule.loan_id, loanNumber: schedule.loan_number, installments: schedule.installments })
          }
        } catch {
          // no loan for this order yet — skip
        }
      }
      setSchedules(results)
    } finally {
      setLoaded(true)
    }
  }

  useEffect(() => {
    // Auth is enforced server-side by middleware.ts before this page ever renders.
    loadSchedules()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const allInstallments: InstallmentWithLoan[] = useMemo(() => schedules.flatMap((s) =>
    s.installments.map((i) => ({
      ...i,
      loanNumber: s.loanNumber,
      daysLeft: Math.ceil((new Date(i.due_date).getTime() - Date.now()) / (1000 * 60 * 60 * 24)),
    }))
  ), [schedules])

  const pending = allInstallments.filter((i) => i.status === "pending").sort((a, b) => a.daysLeft - b.daysLeft)
  const overdue = pending.filter((i) => i.daysLeft < 0)
  const upcoming = pending.filter((i) => i.daysLeft >= 0)
  const history = allInstallments.filter((i) => i.status === "paid").sort((a, b) => (b.paid_at ?? "").localeCompare(a.paid_at ?? ""))

  const totalOutstanding = pending.reduce((sum, i) => sum + i.amount, 0)
  const totalPaid = history.reduce((sum, i) => sum + i.amount, 0)
  const nextDue = pending[0] ?? null

  const handlePay = async () => {
    if (!selectedInstallment || !selectedMethod) return
    setIsPaying(true)
    setError("")
    try {
      await paymentsApi.payInstallment(selectedInstallment.id, selectedMethod, selectedInstallment.amount)
      setSelectedInstallment(null)
      setSelectedMethod("")
      await loadSchedules()
    } catch (err) {
      const message = err instanceof ApiError ? String(err.detail) : "Could not process payment. Please try again."
      setError(message)
    } finally {
      setIsPaying(false)
    }
  }

  if (!loaded) return <RepaymentsSkeleton />

  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto px-4 max-w-6xl">
        <motion.div
          initial={{ y: -20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6 }}
          className="mb-8"
        >
          <h1 className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight mb-1.5">Repayments</h1>
          <p className="text-gray-600 dark:text-gray-400">Track and pay your installments across every active order</p>
        </motion.div>

        {/* Stat cards */}
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {[
            {
              label: "Total Outstanding",
              value: formatCurrency(totalOutstanding),
              subtext: pending.length === 0 ? "Nothing owed right now" : `Across ${pending.length} installment${pending.length > 1 ? "s" : ""}`,
              icon: Wallet,
              color: "from-orange-500 to-amber-600",
            },
            {
              label: "Next Payment",
              value: nextDue ? formatCurrency(nextDue.amount) : "—",
              subtext: nextDue
                ? (nextDue.daysLeft < 0 ? `Overdue by ${Math.abs(nextDue.daysLeft)} day${Math.abs(nextDue.daysLeft) > 1 ? "s" : ""}` : `Due ${new Date(nextDue.due_date).toLocaleDateString(undefined, { month: "long", day: "numeric" })}`)
                : "No payments due",
              icon: CalendarClock,
              color: overdue.length > 0 ? "from-red-500 to-rose-600" : "from-sky-500 to-indigo-600",
            },
            {
              label: "Total Paid",
              value: formatCurrency(totalPaid),
              subtext: history.length === 0 ? "No payments recorded yet" : `${history.length} installment${history.length > 1 ? "s" : ""} paid`,
              icon: TrendingUp,
              color: "from-emerald-500 to-teal-600",
            },
            {
              label: "Payment Record",
              value: (history.length + overdue.length) === 0 ? "—" : `${history.length}/${history.length + overdue.length + upcoming.length}`,
              subtext: overdue.length === 0 ? "No overdue amounts" : `${overdue.length} overdue`,
              icon: overdue.length === 0 ? CheckCircle2 : AlertTriangle,
              color: overdue.length === 0 ? "from-emerald-500 to-teal-600" : "from-red-500 to-rose-600",
            },
          ].map((stat, index) => {
            const StatIcon = stat.icon
            return (
              <motion.div key={stat.label} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: index * 0.08 }}>
                <Card className="card-surface h-full">
                  <CardContent className="p-6">
                    <div className={`w-11 h-11 bg-gradient-to-br ${stat.color} rounded-xl flex items-center justify-center shadow-lg mb-4`}>
                      <StatIcon className="w-5 h-5 text-white" />
                    </div>
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">{stat.label}</p>
                    <h3 className="text-2xl font-black text-gray-900 dark:text-white tracking-tight tabular-nums">{stat.value}</h3>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mt-1.5">{stat.subtext}</p>
                  </CardContent>
                </Card>
              </motion.div>
            )
          })}
        </div>

        <div className="grid lg:grid-cols-3 gap-8">
          <motion.div
            initial={{ x: -30, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.15 }}
            className="lg:col-span-2"
          >
            <Card className="card-surface">
              <CardContent className="p-6">
                <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-5">Select an Installment</h3>

                {pending.length === 0 ? (
                  <div className="text-center py-10">
                    <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 bg-emerald-500/10">
                      <CheckCircle2 className="w-8 h-8 text-emerald-500" />
                    </div>
                    <p className="text-gray-500">You&apos;re all caught up — no pending installments.</p>
                  </div>
                ) : (
                  <div className="space-y-3 mb-6">
                    {overdue.length > 0 && (
                      <p className="text-xs font-bold uppercase tracking-wide text-red-500 mb-1">Overdue</p>
                    )}
                    {overdue.map((inst) => (
                      <InstallmentRow key={`${inst.loanNumber}-${inst.number}`} inst={inst} selected={selectedInstallment} onSelect={setSelectedInstallment} overdue />
                    ))}
                    {upcoming.length > 0 && (
                      <p className={`text-xs font-bold uppercase tracking-wide text-gray-500 mb-1 ${overdue.length > 0 ? "pt-2" : ""}`}>Upcoming</p>
                    )}
                    {upcoming.map((inst) => (
                      <InstallmentRow key={`${inst.loanNumber}-${inst.number}`} inst={inst} selected={selectedInstallment} onSelect={setSelectedInstallment} overdue={false} />
                    ))}
                  </div>
                )}

                {selectedInstallment && (
                  <div className="mb-6">
                    <label className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 block">Payment Method</label>
                    <div className="space-y-3">
                      {METHODS.map((method) => (
                        <div
                          key={method.id}
                          onClick={() => setSelectedMethod(method.id)}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(e) => e.key === "Enter" && setSelectedMethod(method.id)}
                          className={`border rounded-xl p-4 cursor-pointer transition-all duration-200 ${
                            selectedMethod === method.id ? "border-orange-500 bg-orange-500/5" : "border-gray-200 dark:border-white/10 hover:border-orange-500/30"
                          }`}
                        >
                          <div className="flex items-center gap-4">
                            <div className={`w-11 h-11 bg-gradient-to-br ${method.color} rounded-xl flex items-center justify-center flex-none`}>
                              <method.icon className="w-5 h-5 text-white" />
                            </div>
                            <div>
                              <h4 className="font-semibold text-gray-900 dark:text-white text-sm">{method.name}</h4>
                              <p className="text-xs text-gray-500">{method.description}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {error && (
                  <div className="mb-4 flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                    <AlertCircle className="w-4 h-4 flex-none" /> {error}
                  </div>
                )}

                <Button
                  onClick={handlePay}
                  disabled={!selectedInstallment || !selectedMethod || isPaying}
                  className="w-full h-14 rounded-xl font-bold bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 shadow-lg shadow-orange-500/10 btn-smooth disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {isPaying ? "Processing…" : selectedInstallment ? `Pay ${formatCurrency(selectedInstallment.amount)}` : "Proceed to Payment"}
                  <ArrowRight className="w-5 h-5" />
                </Button>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div initial={{ x: 30, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ duration: 0.5, delay: 0.25 }}>
            <Card className="card-surface">
              <CardContent className="p-6">
                <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-5">Payment History</h3>
                {history.length === 0 ? (
                  <p className="text-sm text-gray-500 py-4 text-center">No payments recorded yet.</p>
                ) : (
                  <div className="space-y-3">
                    {history.map((payment) => (
                      <div key={`${payment.loanNumber}-${payment.number}`} className="flex items-center justify-between p-3.5 bg-gray-50/50 dark:bg-white/5 rounded-xl border border-gray-100 dark:border-white/5">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-full flex items-center justify-center bg-emerald-500/10 flex-none">
                            <CheckCircle2 className="w-4.5 h-4.5 text-emerald-500" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-gray-900 dark:text-white">Installment #{payment.number}</p>
                            <p className="text-xs text-gray-500">{payment.loanNumber} • {payment.paid_at ? new Date(payment.paid_at).toLocaleDateString() : "—"}</p>
                          </div>
                        </div>
                        <p className="text-sm font-bold text-gray-900 dark:text-white tabular-nums">{formatCurrency(payment.amount)}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>
        </div>
      </div>
    </div>
  )
}

function InstallmentRow({
  inst,
  selected,
  onSelect,
  overdue,
}: {
  inst: InstallmentWithLoan
  selected: InstallmentWithLoan | null
  onSelect: (i: InstallmentWithLoan) => void
  overdue: boolean
}) {
  const isSelected = selected?.number === inst.number && selected?.loanNumber === inst.loanNumber
  const timeLabel = overdue
    ? `Overdue by ${Math.abs(inst.daysLeft)} day${Math.abs(inst.daysLeft) > 1 ? "s" : ""}`
    : inst.daysLeft === 0
      ? "Due today"
      : `${inst.daysLeft} day${inst.daysLeft > 1 ? "s" : ""} left`

  return (
    <button
      type="button"
      onClick={() => onSelect(inst)}
      className={`w-full text-left p-4 rounded-xl border transition-all ${
        isSelected
          ? "border-orange-500 bg-orange-500/5"
          : overdue
            ? "border-red-200 dark:border-red-500/20 bg-red-500/5 hover:border-red-400"
            : "border-gray-200 dark:border-white/10 hover:border-gray-300 dark:hover:border-white/20"
      }`}
    >
      <div className="flex justify-between items-center gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-none ${overdue ? "bg-red-500/10 text-red-500" : "bg-orange-500/10 text-orange-500"}`}>
            <Calendar className="w-4.5 h-4.5" />
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-gray-900 dark:text-white text-sm">Installment #{inst.number}</p>
            <p className="text-xs text-gray-500 truncate">{inst.loanNumber} — due {new Date(inst.due_date).toLocaleDateString()}</p>
          </div>
        </div>
        <div className="text-right flex-none">
          <p className="text-base font-bold text-gray-900 dark:text-white tabular-nums">{formatCurrency(inst.amount)}</p>
          <span className={`text-[11px] font-bold uppercase tracking-wide ${overdue ? "text-red-500" : "text-gray-400"}`}>{timeLabel}</span>
        </div>
      </div>
    </button>
  )
}
