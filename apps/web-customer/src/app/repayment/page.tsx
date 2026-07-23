"use client"

import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { CreditCard, Smartphone, CheckCircle, AlertCircle, ArrowRight, Banknote } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ordersApi } from "@/lib/orders-api"
import { paymentsApi, type InstallmentDetail, type PaymentMethod } from "@/lib/payments-api"
import { ApiError } from "@/lib/api-client"

interface ScheduleWithLoan {
  loanId: number
  loanNumber: string
  installments: InstallmentDetail[]
}

interface InstallmentWithLoan extends InstallmentDetail {
  loanNumber: string
}

const METHODS: { id: PaymentMethod; name: string; description: string; icon: typeof Banknote; color: string }[] = [
  { id: "raast", name: "Raast Instant Payment", description: "Instant bank transfer via Pakistan's real-time payment system", icon: Banknote, color: "from-green-500 to-green-600" },
  { id: "easypaisa", name: "EasyPaisa", description: "Pay using your EasyPaisa mobile wallet", icon: Smartphone, color: "from-green-600 to-green-700" },
  { id: "jazzcash", name: "JazzCash", description: "Pay using your JazzCash mobile wallet", icon: Smartphone, color: "from-blue-500 to-blue-600" },
  { id: "safepay", name: "Card via Safepay", description: "Visa, Mastercard, or UnionPay", icon: CreditCard, color: "from-purple-500 to-purple-600" },
]

export default function Repayment() {
  const [schedules, setSchedules] = useState<ScheduleWithLoan[]>([])
  const [selectedInstallment, setSelectedInstallment] = useState<InstallmentWithLoan | null>(null)
  const [selectedMethod, setSelectedMethod] = useState<PaymentMethod | "">("")
  const [isPaying, setIsPaying] = useState(false)
  const [error, setError] = useState("")
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    // Auth is enforced server-side by middleware.ts before this page ever renders.
    loadSchedules()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  const allInstallments = schedules.flatMap((s) => s.installments.map((i) => ({ ...i, loanNumber: s.loanNumber })))
  const upcoming = allInstallments.filter((i) => i.status === "pending").sort((a, b) => a.due_date.localeCompare(b.due_date))
  const history = allInstallments.filter((i) => i.status === "paid")
  const totalOutstanding = upcoming.reduce((sum, i) => sum + i.amount, 0)
  const totalPaid = history.reduce((sum, i) => sum + i.amount, 0)

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

  if (!loaded) return null

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 pt-28 pb-8">
        <motion.div
          initial={{ y: -20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6 }}
          className="mb-8"
        >
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Repayment Center</h1>
          <p className="text-gray-600">Manage your installment payments with multiple convenient payment options</p>
        </motion.div>

        <div className="grid lg:grid-cols-3 gap-8">
          <motion.div
            initial={{ x: -50, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="lg:col-span-2"
          >
            <Card className="border-0 shadow-large">
              <CardContent className="p-6">
                <h3 className="text-xl font-bold text-gray-900 mb-6">Select an Installment</h3>

                {upcoming.length === 0 ? (
                  <p className="text-gray-500">No pending installments — you're all caught up.</p>
                ) : (
                  <div className="space-y-3 mb-6">
                    {upcoming.map((inst) => (
                      <button
                        key={`${inst.loanNumber}-${inst.number}`}
                        type="button"
                        onClick={() => setSelectedInstallment(inst)}
                        className={`w-full text-left p-4 rounded-xl border-2 transition-all ${
                          selectedInstallment?.number === inst.number && selectedInstallment?.loanNumber === inst.loanNumber
                            ? "border-orange-500 bg-orange-50"
                            : "border-gray-200 hover:border-gray-300"
                        }`}
                      >
                        <div className="flex justify-between items-center">
                          <div>
                            <p className="font-semibold text-gray-900">Installment #{inst.number}</p>
                            <p className="text-sm text-gray-600">{inst.loanNumber} — due {new Date(inst.due_date).toLocaleDateString()}</p>
                          </div>
                          <p className="text-lg font-bold text-gray-900">PKR {inst.amount.toLocaleString()}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                {selectedInstallment && (
                  <div className="mb-6">
                    <label className="text-sm font-medium text-gray-700 mb-3 block">Payment Method</label>
                    <div className="space-y-3">
                      {METHODS.map((method) => (
                        <div
                          key={method.id}
                          onClick={() => setSelectedMethod(method.id)}
                          className={`border-2 rounded-xl p-4 cursor-pointer transition-all duration-200 ${
                            selectedMethod === method.id ? "border-orange-500 bg-orange-50" : "border-gray-200 hover:border-gray-300"
                          }`}
                        >
                          <div className="flex items-center space-x-4">
                            <div className={`w-12 h-12 bg-gradient-to-br ${method.color} rounded-xl flex items-center justify-center`}>
                              <method.icon className="w-6 h-6 text-white" />
                            </div>
                            <div>
                              <h4 className="font-semibold text-gray-900">{method.name}</h4>
                              <p className="text-sm text-gray-600">{method.description}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {error && (
                  <div className="mb-4 flex items-center gap-2 text-sm text-red-600">
                    <AlertCircle className="w-4 h-4" /> {error}
                  </div>
                )}

                <Button
                  size="xl"
                  onClick={handlePay}
                  disabled={!selectedInstallment || !selectedMethod || isPaying}
                  className="w-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isPaying ? "Processing..." : "Proceed to Payment"}
                  <ArrowRight className="w-5 h-5 ml-2" />
                </Button>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div
            initial={{ x: 50, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.4 }}
          >
            <Card className="border-0 shadow-large">
              <CardContent className="p-6">
                <h3 className="text-xl font-bold text-gray-900 mb-6">Payment Summary</h3>
                <div className="space-y-4">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Total Outstanding</span>
                    <span className="font-semibold">PKR {totalOutstanding.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Next Payment</span>
                    <span className="font-semibold text-orange-600">
                      PKR {upcoming[0] ? upcoming[0].amount.toLocaleString() : 0}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Total Paid</span>
                    <span className="font-semibold text-green-600">PKR {totalPaid.toLocaleString()}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </div>

        <motion.div
          initial={{ y: 50, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.6 }}
          className="mt-8"
        >
          <Card className="border-0 shadow-large">
            <CardContent className="p-6">
              <h3 className="text-xl font-bold text-gray-900 mb-6">Payment History</h3>
              {history.length === 0 ? (
                <p className="text-gray-500">No payments recorded yet.</p>
              ) : (
                <div className="space-y-4">
                  {history.map((payment) => (
                    <div key={`${payment.loanNumber}-${payment.number}`} className="flex items-center justify-between p-4 bg-gray-50 rounded-xl">
                      <div className="flex items-center space-x-4">
                        <div className="w-10 h-10 rounded-full flex items-center justify-center bg-green-100">
                          <CheckCircle className="w-5 h-5 text-green-600" />
                        </div>
                        <div>
                          <p className="font-medium text-gray-900">Installment #{payment.number}</p>
                          <p className="text-sm text-gray-600">{payment.loanNumber} • {payment.paid_at ? new Date(payment.paid_at).toLocaleDateString() : "—"}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold text-gray-900">PKR {payment.amount.toLocaleString()}</p>
                        <span className="inline-block px-2 py-1 rounded-full text-xs font-medium text-green-600 bg-green-100">paid</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  )
}
