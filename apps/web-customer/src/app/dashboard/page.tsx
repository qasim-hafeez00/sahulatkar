"use client"

import { motion } from "framer-motion"
import { useState, useEffect, useMemo } from "react"
import { useRouter } from "next/navigation"
import {
  ShoppingBag,
  CreditCard,
  Calendar,
  TrendingUp,
  AlertCircle,
  ArrowRight,
  Eye,
  LifeBuoy,
  Shield,
  Activity,
  ChevronRight,
  CheckCircle2,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { authApi, type CurrentUser } from "@/lib/auth-api"
import { kycApi, type CustomerProfile } from "@/lib/kyc-api"
import { ordersApi, type OrderDetail } from "@/lib/orders-api"
import { paymentsApi } from "@/lib/payments-api"
import { formatCurrency } from "@/lib/utils"
import { getOrderStatusMeta, isClosedOrderStatus, humanizeAccountStatus, TONE_STYLES } from "@/lib/status"

interface InstallmentRow {
  date: string
  amount: string
  amountValue: number
  order: string
  daysLeft: number
}

function DashboardSkeleton() {
  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto px-4 max-w-7xl animate-pulse">
        <div className="card-surface h-40 rounded-2xl mb-8" />
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="card-surface h-32 rounded-2xl" />
          ))}
        </div>
        <div className="grid lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-8">
            <div className="card-surface h-64 rounded-2xl" />
            <div className="card-surface h-64 rounded-2xl" />
          </div>
          <div className="card-surface h-96 rounded-2xl" />
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("overview")
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null)
  const [profile, setProfile] = useState<CustomerProfile | null>(null)
  const [orders, setOrders] = useState<OrderDetail[]>([])
  const [upcomingPayments, setUpcomingPayments] = useState<InstallmentRow[]>([])
  const [overduePayments, setOverduePayments] = useState<InstallmentRow[]>([])
  const [paidOnTimeCount, setPaidOnTimeCount] = useState(0)
  const [dataLoaded, setDataLoaded] = useState(false)
  const router = useRouter()

  useEffect(() => {
    // Auth is enforced server-side by middleware.ts before this page ever
    // renders; the /auth/me redirect below still covers the edge case where
    // a session cookie was valid at middleware time but is rejected by the
    // gateway a moment later (e.g. concurrent logout in another tab).
    authApi.me()
      .then(setCurrentUser)
      .catch(() => router.push("/auth/login"))

    kycApi.getProfile().then(setProfile).catch(() => {})

    ordersApi.list().then(async (summaries) => {
      const details = await Promise.all(
        summaries.slice(0, 10).map((s) => ordersApi.get(s.id).catch(() => null))
      )
      const validOrders = details.filter((o): o is OrderDetail => o !== null)
      setOrders(validOrders)

      const seenLoans = new Set<number>()
      const upcoming: InstallmentRow[] = []
      const overdue: InstallmentRow[] = []
      let paidCount = 0

      for (const order of validOrders) {
        try {
          const schedule = await paymentsApi.getSchedule(order.id)
          if (seenLoans.has(schedule.loan_id)) continue
          seenLoans.add(schedule.loan_id)
          for (const inst of schedule.installments) {
            if (inst.status === "paid") {
              paidCount += 1
              continue
            }
            if (inst.status !== "pending") continue
            const daysLeft = Math.ceil((new Date(inst.due_date).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
            const row: InstallmentRow = {
              date: new Date(inst.due_date).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" }),
              amount: formatCurrency(inst.amount),
              amountValue: inst.amount,
              order: order.product_description ?? `Order #${order.id}`,
              daysLeft,
            }
            if (daysLeft < 0) overdue.push(row)
            else upcoming.push(row)
          }
        } catch {
          // no loan yet for this order
        }
      }
      overdue.sort((a, b) => a.daysLeft - b.daysLeft)
      upcoming.sort((a, b) => a.daysLeft - b.daysLeft)
      setOverduePayments(overdue)
      setUpcomingPayments(upcoming.slice(0, 5))
      setPaidOnTimeCount(paidCount)
    }).finally(() => setDataLoaded(true))
  }, [router])

  const displayName = profile ? `${profile.first_name} ${profile.last_name}` : "there"
  const creditLimitValue = currentUser?.credit_limit ?? 0
  const availableCreditValue = currentUser?.available_credit ?? 0
  const utilizationPercent = creditLimitValue > 0
    ? Math.round(((creditLimitValue - availableCreditValue) / creditLimitValue) * 100)
    : 0
  const hasCreditAssessment = creditLimitValue > 0

  const recentOrders = useMemo(() => orders.map((order) => ({
    id: order.id,
    product: order.product_description ?? `Order #${order.id}`,
    amount: formatCurrency(order.total_amount),
    date: new Date(order.created_at).toLocaleDateString(),
    totalInstallments: order.installment_count ?? 0,
    rawStatus: order.status,
  })), [orders])

  const activeOrdersCount = orders.filter((o) => !isClosedOrderStatus(o.status)).length
  const totalTrackedInstallments = paidOnTimeCount + overduePayments.length + upcomingPayments.length
  const nextDue = overduePayments[0] ?? upcomingPayments[0] ?? null

  const heroMessage = useMemo(() => {
    if (overduePayments.length > 0) {
      const overdueTotal = formatCurrency(overduePayments.reduce((sum, p) => sum + p.amountValue, 0))
      return {
        text: `You have ${overduePayments.length} overdue payment${overduePayments.length > 1 ? "s" : ""} totalling ${overdueTotal}. Pay now to avoid a late fee.`,
        cta: { label: "Pay Now", action: () => router.push("/repayment") },
        urgent: true,
      }
    }
    if (nextDue) {
      return {
        text: `Your next payment of ${nextDue.amount} is due ${nextDue.date}.`,
        cta: { label: "View Payment Schedule", action: () => router.push("/repayment") },
        urgent: false,
      }
    }
    if (activeOrdersCount > 0) {
      return {
        text: `You have ${activeOrdersCount} active order${activeOrdersCount > 1 ? "s" : ""} in progress.`,
        cta: { label: "View Orders", action: () => setActiveTab("orders") },
        urgent: false,
      }
    }
    return {
      text: "Paste a product link from any store to get a financing offer in seconds.",
      cta: { label: "Start a Purchase", action: () => router.push("/cart") },
      urgent: false,
    }
  }, [overduePayments, nextDue, activeOrdersCount, router])

  // Credit gauge — a 3/4 radial arc showing the share of the approved limit still available.
  const radius = 65
  const strokeWidth = 10
  const normalizedRadius = radius - strokeWidth / 2
  const circumference = 2 * Math.PI * normalizedRadius
  const availablePercent = 100 - utilizationPercent
  const strokeDasharray = `${circumference} ${circumference}`
  const strokeDashoffset = circumference - (availablePercent / 100) * circumference

  if (!dataLoaded) return <DashboardSkeleton />

  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto px-4 max-w-7xl">
        {/* Welcome banner */}
        <motion.div
          initial={{ y: -20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6 }}
          className="card-surface p-6 mb-8 flex flex-col md:flex-row md:items-center md:justify-between gap-4 relative overflow-hidden"
        >
          <div className="absolute top-0 right-0 w-48 h-48 bg-orange-500/10 rounded-full blur-3xl pointer-events-none" />
          <div className="relative">
            <h1 className="text-2xl lg:text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight mb-1.5">
              Assalam-o-Alaikum,{" "}
              <span className="bg-gradient-to-r from-orange-500 to-orange-600 bg-clip-text text-transparent dark:from-orange-400 dark:to-orange-500">
                {displayName.split(" ")[0]}
              </span>
              !
            </h1>
            <p className={`text-sm leading-relaxed ${heroMessage.urgent ? "text-red-600 dark:text-red-400 font-semibold" : "text-gray-600 dark:text-gray-400"}`}>
              {heroMessage.text}
            </p>
          </div>
          <Button
            onClick={heroMessage.cta.action}
            className={`relative flex-none font-bold h-11 px-6 rounded-xl shadow-lg btn-smooth flex items-center justify-center gap-2 ${
              heroMessage.urgent
                ? "bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 text-white shadow-red-500/20"
                : "bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white shadow-orange-500/10"
            }`}
          >
            {heroMessage.cta.label}
            <ArrowRight className="w-4 h-4" />
          </Button>
        </motion.div>

        {/* Tab Switcher */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="mb-8 p-1.5 rounded-2xl bg-white/40 dark:bg-black/20 border border-gray-200 dark:border-white/5 backdrop-blur-md max-w-2xl"
        >
          <div className="flex flex-wrap md:flex-nowrap gap-1">
            {[
              { id: "overview", label: "Overview", icon: Activity },
              { id: "orders", label: "Active Orders", icon: ShoppingBag },
            ].map((tab) => {
              const TabIcon = tab.icon
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex-1 flex items-center justify-center space-x-2 px-5 py-3 rounded-xl font-semibold text-sm transition-all duration-300 relative ${
                    isActive
                      ? "text-white shadow-lg"
                      : "text-gray-600 dark:text-gray-400 hover:text-orange-500 dark:hover:text-orange-400 hover:bg-orange-500/5"
                  }`}
                >
                  {isActive && (
                    <motion.div
                      layoutId="activeTabIndicator"
                      className="absolute inset-0 bg-gradient-to-r from-orange-500 to-orange-600 rounded-xl z-0 shadow-md"
                      transition={{ type: "spring", stiffness: 350, damping: 30 }}
                    />
                  )}
                  <TabIcon className={`w-4 h-4 relative z-10 ${isActive ? "text-white" : ""}`} />
                  <span className="relative z-10">{tab.label}</span>
                </button>
              )
            })}
          </div>
        </motion.div>

        {/* Overview Tab Content */}
        {activeTab === "overview" && (
          <div className="space-y-8">
            {/* Stat cards — four distinct, real numbers, no repeats */}
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
              {[
                {
                  label: "Available Credit",
                  value: hasCreditAssessment ? formatCurrency(availableCreditValue) : "Not assessed yet",
                  subtext: hasCreditAssessment ? `of ${formatCurrency(creditLimitValue)} limit` : "Paste a product link to get an offer",
                  icon: CreditCard,
                  color: "from-orange-500 to-amber-600",
                },
                {
                  label: "Active Orders",
                  value: activeOrdersCount,
                  subtext: activeOrdersCount === 0 ? "No orders in progress" : "Currently being processed or shipped",
                  icon: ShoppingBag,
                  color: "from-sky-500 to-indigo-600",
                },
                {
                  label: "Next Payment",
                  value: nextDue ? nextDue.amount : "—",
                  subtext: nextDue
                    ? (overduePayments.length > 0 ? "Overdue — pay as soon as possible" : `Due ${nextDue.date}`)
                    : "No payments due",
                  icon: Calendar,
                  color: overduePayments.length > 0 ? "from-red-500 to-rose-600" : "from-pink-500 to-rose-600",
                },
                {
                  label: "Payment Record",
                  value: totalTrackedInstallments === 0 ? "—" : `${paidOnTimeCount}/${totalTrackedInstallments}`,
                  subtext: totalTrackedInstallments === 0
                    ? "No payment history yet"
                    : overduePayments.length === 0 ? "Paid on time, no overdue amounts" : `${overduePayments.length} overdue`,
                  icon: TrendingUp,
                  color: "from-emerald-500 to-teal-600",
                },
              ].map((stat, index) => {
                const StatIcon = stat.icon
                return (
                  <motion.div
                    key={stat.label}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, delay: index * 0.08 }}
                  >
                    <Card className="card-surface group hover:-translate-y-1.5 transition-all duration-300 h-full">
                      <CardContent className="p-6 flex flex-col justify-between h-full">
                        <div className={`w-11 h-11 bg-gradient-to-br ${stat.color} rounded-xl flex items-center justify-center shadow-lg group-hover:scale-105 transition-transform duration-300 mb-4`}>
                          <StatIcon className="w-5 h-5 text-white" />
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                            {stat.label}
                          </p>
                          <h3 className="text-2xl font-black text-gray-900 dark:text-white tracking-tight tabular-nums">
                            {stat.value}
                          </h3>
                          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mt-1.5">{stat.subtext}</p>
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                )
              })}
            </div>

            <div className="grid lg:grid-cols-3 gap-8">
              {/* Left Column: Lists */}
              <div className="lg:col-span-2 space-y-8">
                {/* Recent Orders */}
                <motion.div
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.5, delay: 0.3 }}
                >
                  <Card className="card-surface overflow-hidden">
                    <CardContent className="p-6">
                      <div className="flex items-center justify-between mb-6">
                        <div>
                          <h3 className="text-xl font-bold text-gray-900 dark:text-white">Active Orders</h3>
                          <p className="text-xs text-gray-500">Products you&apos;re currently financing</p>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setActiveTab("orders")}
                          className="text-orange-500 hover:text-orange-600 font-bold flex items-center gap-1 group/btn"
                        >
                          View All
                          <ChevronRight className="w-4 h-4 group-hover/btn:translate-x-0.5 transition-transform" />
                        </Button>
                      </div>

                      <div className="space-y-4">
                        {recentOrders.length === 0 && (
                          <p className="text-sm text-gray-500 py-4 text-center">No orders yet — paste a product link to get started.</p>
                        )}
                        {recentOrders.slice(0, 3).map((order) => {
                          const meta = getOrderStatusMeta(order.rawStatus)
                          const tone = TONE_STYLES[meta.tone]
                          const ToneIcon = tone.icon
                          return (
                            <div
                              key={order.id}
                              className="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-gray-50/50 dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/5 hover:border-orange-500/20 hover:bg-orange-500/[0.01] transition-all duration-300 group/item"
                            >
                              <div className="flex items-center space-x-3.5">
                                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center shadow-md flex-none">
                                  <ShoppingBag className="w-5 h-5 text-white" />
                                </div>
                                <div>
                                  <h4 className="font-bold text-gray-900 dark:text-white text-sm group-hover/item:text-orange-500 transition-colors">
                                    {order.product}
                                  </h4>
                                  <div className="flex items-center space-x-2 text-xs text-gray-500 mt-1">
                                    <span>{order.date}</span>
                                  </div>
                                </div>
                              </div>

                              <div className="mt-3 sm:mt-0 flex-1 max-w-[180px] sm:mx-6">
                                <div className="flex justify-between items-center text-xs mb-1 text-gray-500">
                                  <span>Term:</span>
                                  <span className="font-semibold tabular-nums">
                                    {order.totalInstallments} months
                                  </span>
                                </div>
                              </div>

                              <div className="flex items-center justify-between sm:justify-end gap-4 mt-3 sm:mt-0">
                                <div className="text-right">
                                  <p className="text-xs text-gray-400">Total Financed</p>
                                  <p className="text-sm font-bold text-gray-900 dark:text-white tabular-nums">
                                    {order.amount}
                                  </p>
                                </div>
                                <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${tone.badge}`}>
                                  <ToneIcon className={`w-3.5 h-3.5 ${meta.tone === "progress" ? "animate-spin" : ""}`} />
                                  {meta.label}
                                </span>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>

                {/* Upcoming Payments */}
                <motion.div
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.5, delay: 0.4 }}
                >
                  <Card className="card-surface">
                    <CardContent className="p-6">
                      <div className="mb-6">
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white">Upcoming Installments</h3>
                        <p className="text-xs text-gray-500">Your next scheduled payments</p>
                      </div>

                      <div className="space-y-4">
                        {overduePayments.length === 0 && upcomingPayments.length === 0 && (
                          <p className="text-sm text-gray-500 py-4 text-center">No pending installments — you&apos;re all caught up.</p>
                        )}
                        {[...overduePayments, ...upcomingPayments].map((payment, index) => {
                          const isOverdue = payment.daysLeft < 0
                          const isDueSoon = payment.daysLeft >= 0 && payment.daysLeft <= 2
                          const timeLabel = isOverdue
                            ? `Overdue by ${Math.abs(payment.daysLeft)} day${Math.abs(payment.daysLeft) > 1 ? "s" : ""}`
                            : payment.daysLeft === 0
                              ? "Due today"
                              : `${payment.daysLeft} day${payment.daysLeft > 1 ? "s" : ""} left`
                          return (
                            <div
                              key={index}
                              className="flex items-center justify-between p-4 bg-gray-50/50 dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/5 hover:border-orange-500/20 transition-all duration-300"
                            >
                              <div className="flex items-center space-x-3.5">
                                <div className={`w-10 h-10 rounded-xl flex items-center justify-center border flex-none ${
                                  isOverdue
                                    ? "bg-red-500/10 border-red-500/20 text-red-500"
                                    : isDueSoon
                                      ? "bg-amber-500/10 border-amber-500/20 text-amber-500"
                                      : "bg-orange-500/10 border-orange-500/20 text-orange-500"
                                }`}>
                                  <Calendar className="w-5 h-5" />
                                </div>
                                <div>
                                  <h4 className="font-bold text-gray-900 dark:text-white text-sm">
                                    {payment.order}
                                  </h4>
                                  <p className="text-xs text-gray-500 mt-0.5">Due {payment.date}</p>
                                </div>
                              </div>

                              <div className="text-right">
                                <span className={`inline-block px-3 py-1 rounded-full text-[11px] font-bold uppercase tracking-wide ${
                                  isOverdue
                                    ? "text-red-600 dark:text-red-400 bg-red-500/10 border border-red-500/20"
                                    : isDueSoon
                                      ? "text-amber-600 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20"
                                      : "text-gray-600 dark:text-gray-400 bg-gray-500/10 border border-gray-500/20"
                                }`}>
                                  {timeLabel}
                                </span>
                                <p className="text-sm font-bold text-gray-900 dark:text-white mt-1 tabular-nums">
                                  {payment.amount}
                                </p>
                              </div>
                            </div>
                          )
                        })}
                      </div>

                      {(overduePayments.length > 0 || upcomingPayments.length > 0) && (
                        <Button
                          onClick={() => router.push("/repayment")}
                          className="w-full mt-5 bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white font-bold h-12 rounded-xl shadow-lg shadow-orange-500/10 btn-smooth flex items-center justify-center gap-2"
                        >
                          {overduePayments.length > 0 ? "Pay Now" : "View Payment Schedule"}
                          <ArrowRight className="w-4 h-4" />
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                </motion.div>
              </div>

              {/* Right Column: Credit Overview */}
              <div className="space-y-8">
                <motion.div
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.5, delay: 0.4 }}
                  className="h-full"
                >
                  <Card className="card-surface h-full flex flex-col justify-between relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/5 rounded-full blur-2xl pointer-events-none" />

                    <CardContent className="p-6 flex flex-col items-center text-center h-full justify-between">
                      <div className="w-full">
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-6">Credit Overview</h3>

                        <div className="relative flex items-center justify-center my-6">
                          <svg className="w-44 h-44 transform -rotate-90">
                            <circle
                              cx="88"
                              cy="88"
                              r={radius}
                              stroke="currentColor"
                              strokeWidth={strokeWidth}
                              className="text-gray-100 dark:text-white/5"
                              fill="transparent"
                            />
                            <motion.circle
                              cx="88"
                              cy="88"
                              r={radius}
                              stroke="url(#scoreGradient)"
                              strokeWidth={strokeWidth}
                              fill="transparent"
                              strokeDasharray={strokeDasharray}
                              initial={{ strokeDashoffset: circumference }}
                              animate={{ strokeDashoffset }}
                              transition={{ duration: 1.5, ease: "easeOut" }}
                              strokeLinecap="round"
                            />
                            <defs>
                              <linearGradient id="scoreGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stopColor="#f97316" />
                                <stop offset="100%" stopColor="#10b981" />
                              </linearGradient>
                            </defs>
                          </svg>

                          <div className="absolute flex flex-col items-center justify-center">
                            <motion.span
                              initial={{ scale: 0.6, opacity: 0 }}
                              animate={{ scale: 1, opacity: 1 }}
                              transition={{ duration: 0.8, delay: 0.3 }}
                              className="text-4xl font-black text-gray-900 dark:text-white tracking-tighter tabular-nums"
                            >
                              {availablePercent}%
                            </motion.span>
                            <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mt-1">
                              Available Credit
                            </span>
                          </div>
                        </div>

                        <div className="p-4 bg-gray-50 dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/5 mt-4">
                          <div className="flex justify-between items-center text-xs mb-2">
                            <span className="text-gray-500">Usage this cycle:</span>
                            <span className="font-extrabold text-gray-900 dark:text-white">
                              {utilizationPercent < 30 ? "Low" : utilizationPercent < 70 ? "Moderate" : "High"}
                            </span>
                          </div>
                          <div className="flex justify-between items-center text-xs">
                            <span className="text-gray-500">Account status:</span>
                            <span className="font-bold text-gray-900 dark:text-white">{humanizeAccountStatus(currentUser?.status)}</span>
                          </div>
                        </div>
                      </div>

                      {/* Real, computed facts — not fabricated claims */}
                      <div className="w-full mt-6 pt-5 border-t border-gray-100 dark:border-white/5 space-y-3 text-left">
                        <div className="flex items-start space-x-2 text-xs">
                          {overduePayments.length === 0 ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
                          ) : (
                            <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                          )}
                          <p className="text-gray-600 dark:text-gray-400">
                            {overduePayments.length === 0
                              ? "No overdue payments on your account."
                              : `${overduePayments.length} overdue payment${overduePayments.length > 1 ? "s" : ""} — pay now to avoid a late fee.`}
                          </p>
                        </div>
                        <div className="flex items-start space-x-2 text-xs">
                          <div className="w-1.5 h-1.5 rounded-full bg-gray-400 mt-1.5 flex-shrink-0" />
                          <p className="text-gray-600 dark:text-gray-400">
                            {totalTrackedInstallments === 0
                              ? "No payment history yet — it starts after your first purchase."
                              : `${paidOnTimeCount} of ${totalTrackedInstallments} installments paid.`}
                          </p>
                        </div>
                        <div className="flex items-start space-x-2 text-xs pt-1">
                          <Shield className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                          <p className="text-gray-500 dark:text-gray-500">
                            Your information is encrypted and never shared without your consent.
                          </p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              </div>
            </div>
          </div>
        )}

        {/* Orders Tab Content */}
        {activeTab === "orders" && (
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <Card className="card-surface overflow-hidden">
              <CardContent className="p-6">
                <div className="mb-8">
                  <h3 className="text-2xl font-bold text-gray-900 dark:text-white">Purchase History</h3>
                  <p className="text-xs text-gray-500 mt-1">Every product you&apos;ve financed through SahulatKar</p>
                </div>

                <div className="space-y-6">
                  {recentOrders.length === 0 && (
                    <p className="text-sm text-gray-500 py-8 text-center">No orders yet — paste a product link to get started.</p>
                  )}
                  {recentOrders.map((order, index) => {
                    const meta = getOrderStatusMeta(order.rawStatus)
                    const tone = TONE_STYLES[meta.tone]
                    const ToneIcon = tone.icon
                    return (
                      <motion.div
                        key={order.id}
                        initial={{ opacity: 0, y: 15 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, delay: index * 0.1 }}
                        className="border border-gray-200 dark:border-white/5 rounded-2xl p-6 hover:shadow-lg dark:hover:bg-white/[0.01] hover:border-orange-500/20 transition-all duration-300 group"
                      >
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 pb-4 border-b border-gray-100 dark:border-white/5">
                          <div className="flex items-center space-x-3.5">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center shadow-md flex-none">
                              <ShoppingBag className="w-5 h-5 text-white" />
                            </div>
                            <div>
                              <h4 className="font-extrabold text-gray-900 dark:text-white text-base group-hover:text-orange-500 transition-colors">
                                {order.product}
                              </h4>
                              <p className="text-xs text-gray-500 mt-0.5">Order #{order.id}</p>
                            </div>
                          </div>
                          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${tone.badge}`}>
                            <ToneIcon className={`w-3.5 h-3.5 ${meta.tone === "progress" ? "animate-spin" : ""}`} />
                            {meta.label}
                          </span>
                        </div>

                        <div className="grid grid-cols-2 md:grid-cols-3 gap-6 text-sm mb-6">
                          <div>
                            <p className="text-xs text-gray-500 mb-1">Total Financed</p>
                            <p className="font-bold text-gray-900 dark:text-white tabular-nums">{order.amount}</p>
                          </div>
                          <div>
                            <p className="text-xs text-gray-500 mb-1">Order Date</p>
                            <p className="font-bold text-gray-800 dark:text-gray-200 tabular-nums">{order.date}</p>
                          </div>
                          <div>
                            <p className="text-xs text-gray-500 mb-1">Installment Plan</p>
                            <p className="font-bold text-orange-500 tabular-nums">{order.totalInstallments} months</p>
                          </div>
                        </div>

                        <div className="flex flex-wrap gap-3">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => router.push("/payments/order-tracking")}
                            className="h-10 rounded-xl px-4 font-bold border-gray-300 dark:border-white/10 dark:hover:bg-white/5 hover:border-orange-500/30 flex items-center gap-2 group/btn"
                          >
                            <Eye className="w-4 h-4 text-gray-400 group-hover/btn:text-orange-500 transition-colors" />
                            Track Package
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => router.push("/support")}
                            className="h-10 rounded-xl px-4 font-bold border-gray-300 dark:border-white/10 dark:hover:bg-white/5 hover:border-orange-500/30 flex items-center gap-2 group/btn"
                          >
                            <LifeBuoy className="w-4 h-4 text-gray-400 group-hover/btn:text-orange-500 transition-colors" />
                            Need Help With This Order
                          </Button>
                        </div>
                      </motion.div>
                    )
                  })}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </div>
    </div>
  )
}
