"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Check, ArrowRight } from "lucide-react"
import { ordersApi, type OrderDetail } from "@/lib/orders-api"
import { paymentsApi, type PaymentSchedule } from "@/lib/payments-api"

export default function OrderSuccess() {
  const [animateIn, setAnimateIn] = useState(false)
  const [orders, setOrders] = useState<OrderDetail[]>([])
  const [schedule, setSchedule] = useState<PaymentSchedule | null>(null)
  const router = useRouter()

  useEffect(() => {
    setAnimateIn(true)
    const raw = sessionStorage.getItem("sk_cart_order_ids")
    if (!raw) return
    const orderIds: number[] = JSON.parse(raw)
    Promise.all(orderIds.map((id) => ordersApi.get(id))).then(setOrders).catch(() => {})
    if (orderIds[0]) {
      paymentsApi.getSchedule(orderIds[0]).then(setSchedule).catch(() => {})
    }
  }, [])

  const totalAmount = orders.reduce((sum, o) => sum + o.total_amount, 0)
  const nextInstallment = schedule?.installments.find((i) => i.status === "pending")

  return (
    <div className="min-h-screen pt-24 pb-16">
      <div className="mx-auto max-w-3xl px-4 py-12 lg:px-8">
        <div className="flex justify-center mb-8">
          <div className="inline-flex items-center gap-2 bg-orange-100 border border-orange-200 rounded-full px-4 py-2">
            <span className="w-2 h-2 rounded-full bg-orange-500" />
            <span className="text-xs font-semibold text-orange-700 uppercase tracking-wider">VERIFIED</span>
          </div>
        </div>

        <div className="text-center space-y-6 mb-12">
          <div className={`transition-all duration-700 ${animateIn ? "scale-100 opacity-100" : "scale-75 opacity-0"}`}>
            <div className="w-24 h-24 mx-auto bg-emerald-100 rounded-full flex items-center justify-center">
              <Check className="w-12 h-12 text-emerald-600" strokeWidth={3} />
            </div>
          </div>

          <h1 className="text-4xl font-bold text-slate-900">Order Placed Successfully</h1>
          <p className="text-slate-600 text-lg">Your {orders.length}-item purchase has been financed and confirmed.</p>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 shadow-lg overflow-hidden mb-8">
          <div className="px-8 py-6 bg-gradient-to-r from-slate-50 to-orange-50 border-b border-slate-200">
            <p className="text-xs uppercase tracking-widest text-slate-600 font-semibold">Orders</p>
            <p className="text-2xl font-bold text-slate-900 font-mono mt-2">
              {orders.map((o) => `#${o.id}`).join(", ") || "Loading..."}
            </p>
          </div>

          <div className="p-8 space-y-6">
            <div className="grid md:grid-cols-2 gap-6">
              <div className="space-y-4">
                {orders.map((order) => (
                  <div key={order.id} className="flex items-start gap-4">
                    <div className="text-3xl">📦</div>
                    <div>
                      <p className="text-sm uppercase tracking-wider text-slate-500 font-semibold">Order #{order.id}</p>
                      <p className="text-lg font-bold text-slate-900">PKR {order.total_amount.toLocaleString()}</p>
                      <p className="text-sm text-slate-600 capitalize">{order.status.replace(/_/g, " ")}</p>
                    </div>
                  </div>
                ))}
              </div>

              <div className="bg-slate-900 text-white rounded-2xl p-6 space-y-4">
                <div>
                  <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold mb-1">Combined Financing Plan</p>
                  {schedule ? (
                    <div className="flex items-baseline gap-2">
                      <span className="text-3xl font-bold">Rs {Math.round(schedule.installments[0]?.amount ?? 0).toLocaleString()}</span>
                      <span className="text-sm text-slate-400">/month</span>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-400">Loading schedule...</p>
                  )}
                </div>

                <div className="border-t border-slate-700 pt-4 space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">Total Purchase Value</span>
                    <span className="font-semibold">PKR {totalAmount.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">Installments</span>
                    <span className="font-semibold">{schedule?.installments.length ?? "—"} months</span>
                  </div>
                </div>

                {nextInstallment && (
                  <p className="text-xs text-slate-400 pt-2">
                    Next installment due {new Date(nextInstallment.due_date).toLocaleDateString()}.
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-4 mb-8">
          <button
            type="button"
            onClick={() => router.push("/dashboard")}
            className="px-6 py-3 bg-orange-500 hover:bg-orange-600 text-white rounded-2xl font-semibold transition btn-smooth"
          >
            Continue to Dashboard
          </button>
          <button
            type="button"
            onClick={() => router.push("/payments/order-tracking")}
            className="px-6 py-3 bg-slate-900 hover:bg-slate-950 text-white rounded-2xl font-semibold transition flex items-center justify-center gap-2 btn-smooth shadow-md"
          >
            Track Shariah Order
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
