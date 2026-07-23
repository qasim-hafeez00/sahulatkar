"use client"

import { motion } from "framer-motion"
import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import {
  User,
  ShoppingBag,
  CreditCard,
  Calendar,
  TrendingUp,
  AlertCircle,
  ArrowRight,
  Eye,
  Download,
  Settings,
  Shield,
  Award,
  Clock,
  Cpu,
  QrCode,
  Activity,
  DollarSign,
  ChevronRight,
  ExternalLink,
  CheckCircle2,
  Truck,
  RefreshCw,
  Percent
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { authApi, type CurrentUser } from "@/lib/auth-api"
import { kycApi, type CustomerProfile } from "@/lib/kyc-api"
import { ordersApi, type OrderDetail } from "@/lib/orders-api"
import { paymentsApi } from "@/lib/payments-api"
import { formatCurrency } from "@/lib/utils"

interface UpcomingInstallment {
  date: string
  amount: string
  order: string
  daysLeft: number
}

function formatOrderStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

function isDeliveredStatus(status: string): boolean {
  return status === "delivered" || status === "completed"
}

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("overview")
  const [currentTime, setCurrentTime] = useState("")
  const [currentDate, setCurrentDate] = useState("")
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null)
  const [profile, setProfile] = useState<CustomerProfile | null>(null)
  const [orders, setOrders] = useState<OrderDetail[]>([])
  const [upcomingPayments, setUpcomingPayments] = useState<UpcomingInstallment[]>([])
  const [dataLoaded, setDataLoaded] = useState(false)
  const router = useRouter()

  useEffect(() => {
    const updateDateTime = () => {
      const now = new Date()
      setCurrentTime(now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }))
      setCurrentDate(now.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric", year: "numeric" }))
    }
    updateDateTime()
    const timer = setInterval(updateDateTime, 1000)
    return () => clearInterval(timer)
  }, [])

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
      const pending: UpcomingInstallment[] = []
      for (const order of validOrders) {
        try {
          const schedule = await paymentsApi.getSchedule(order.id)
          if (seenLoans.has(schedule.loan_id)) continue
          seenLoans.add(schedule.loan_id)
          for (const inst of schedule.installments) {
            if (inst.status !== "pending") continue
            const daysLeft = Math.ceil((new Date(inst.due_date).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
            pending.push({
              date: new Date(inst.due_date).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" }),
              amount: formatCurrency(inst.amount),
              order: order.product_description ?? `Order #${order.id}`,
              daysLeft,
            })
          }
        } catch {
          // no loan yet for this order
        }
      }
      pending.sort((a, b) => a.daysLeft - b.daysLeft)
      setUpcomingPayments(pending.slice(0, 5))
    }).finally(() => setDataLoaded(true))
  }, [router])

  const userProfile = {
    name: profile ? `${profile.first_name} ${profile.last_name}` : "there",
    email: "Not provided",
    phone: currentUser?.phone ?? "—",
    cnic: profile?.cnic ?? "Pending verification",
    creditLimit: currentUser ? formatCurrency(currentUser.credit_limit ?? 0) : "PKR 0",
    availableCredit: currentUser ? formatCurrency(currentUser.available_credit) : "PKR 0",
  }

  const creditLimitValue = currentUser?.credit_limit ?? 0
  const availableCreditValue = currentUser?.available_credit ?? 0
  const utilizationPercent = creditLimitValue > 0
    ? Math.round(((creditLimitValue - availableCreditValue) / creditLimitValue) * 100)
    : 0

  const recentOrders = orders.map((order) => ({
    id: order.id,
    product: order.product_description ?? `Order #${order.id}`,
    amount: formatCurrency(order.total_amount),
    status: formatOrderStatus(order.status),
    rawStatus: order.status,
    date: new Date(order.created_at).toLocaleDateString(),
    totalInstallments: order.installment_count ?? 0,
  }))

  const getStatusIcon = (rawStatus: string) => {
    if (isDeliveredStatus(rawStatus)) return <CheckCircle2 className="w-4 h-4 text-emerald-500" />
    if (rawStatus === "delivery_pending") return <Truck className="w-4 h-4 text-amber-500" />
    if (rawStatus === "cancelled" || rawStatus === "rejected") return <AlertCircle className="w-4 h-4 text-red-500" />
    return <RefreshCw className="w-4 h-4 text-sky-500 animate-spin" />
  }

  const getStatusColor = (rawStatus: string) => {
    if (isDeliveredStatus(rawStatus)) return "text-emerald-500 bg-emerald-500/10 border-emerald-500/20"
    if (rawStatus === "delivery_pending") return "text-amber-500 bg-amber-500/10 border-amber-500/20"
    if (rawStatus === "cancelled" || rawStatus === "rejected") return "text-red-500 bg-red-500/10 border-red-500/20"
    return "text-sky-400 bg-sky-400/10 border-sky-400/20"
  }

  const getOrderIcon = () => (
    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center shadow-md">
      <ShoppingBag className="w-5 h-5 text-white" />
    </div>
  )

  // Credit Gauge Variables — driven by real credit utilization, not a fabricated score
  const minScore = 0
  const maxScore = 100
  const userScore = utilizationPercent
  const scorePercent = utilizationPercent
  // SVG Arc Configurations
  const radius = 65
  const strokeWidth = 10
  const normalizedRadius = radius - strokeWidth / 2
  const circumference = 2 * Math.PI * normalizedRadius
  // Make the circle a 3/4 gauge (dasharray: 270 deg of circle)
  const strokeDasharray = `${circumference} ${circumference}`
  const strokeDashoffset = circumference - (scorePercent / 100) * circumference

  if (!dataLoaded) return null

  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto px-4 max-w-7xl">
        {/* Welcome Section / Telemetry HUD */}
        <div className="grid lg:grid-cols-3 gap-6 mb-8 items-stretch">
          <motion.div
            initial={{ y: -20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.6 }}
            className="lg:col-span-2 card-surface p-6 flex flex-col justify-between relative overflow-hidden group"
          >
            {/* Background glowing decorations */}
            <div className="absolute top-0 right-0 w-48 h-48 bg-orange-500/10 rounded-full blur-3xl pointer-events-none group-hover:bg-orange-500/15 transition-all duration-500" />
            <div className="absolute -bottom-8 -left-8 w-32 h-32 bg-pink-500/5 rounded-full blur-2xl pointer-events-none" />

            <div>
              <div className="flex items-center space-x-2.5 mb-3">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-xs font-mono tracking-wider text-emerald-600 dark:text-emerald-400 font-semibold uppercase">
                  Secured FinTech Node Active
                </span>
              </div>
              <h1 className="text-3xl lg:text-4xl font-extrabold text-gray-900 dark:text-white tracking-tight mb-2">
                Assalam-o-Alaikum,{" "}
                <span className="bg-gradient-to-r from-orange-500 to-orange-600 bg-clip-text text-transparent dark:from-orange-400 dark:to-orange-500">
                  {userProfile.name.split(" ")[0]}
                </span>
                !
              </h1>
              <p className="text-gray-600 dark:text-gray-400 max-w-xl text-sm leading-relaxed">
                Welcome back to your premium SahulatKar dashboard. Your Shariah-compliant financing pipeline is optimized, active, and fully cleared.
              </p>
            </div>

            <div className="flex items-center space-x-6 mt-6 pt-6 border-t border-gray-200 dark:border-white/5">
              <div className="flex items-center space-x-2">
                <Shield className="w-5 h-5 text-orange-500" />
                <div>
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider font-mono">Secured With</p>
                  <p className="text-xs font-bold text-gray-800 dark:text-gray-200">AES-256 Protocol</p>
                </div>
              </div>
              <div className="w-px h-8 bg-gray-200 dark:bg-white/5" />
              <div className="flex items-center space-x-2">
                <Award className="w-5 h-5 text-orange-500" />
                <div>
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider font-mono">Account Tier</p>
                  <p className="text-xs font-bold text-gray-800 dark:text-gray-200">Platinum Premium</p>
                </div>
              </div>
            </div>
          </motion.div>

          <motion.div
            initial={{ y: -20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="card-surface p-6 flex flex-col justify-between relative overflow-hidden bg-gradient-to-br from-slate-900 via-slate-950 to-orange-950/20 text-white border-slate-800"
          >
            <div className="absolute top-0 right-0 w-24 h-24 bg-orange-500/10 rounded-full blur-2xl pointer-events-none" />
            <div className="flex justify-between items-start mb-4">
              <div>
                <span className="text-[10px] uppercase font-mono tracking-widest text-orange-400/80">
                  SYSTEM TIME (PKT)
                </span>
                <h3 className="text-3xl font-mono font-extrabold tracking-widest text-orange-400 mt-1 drop-shadow-[0_0_8px_rgba(249,115,22,0.3)]">
                  {currentTime || "00:00:00"}
                </h3>
              </div>
              <div className="p-2 rounded-xl bg-white/5 border border-white/10">
                <Clock className="w-5 h-5 text-orange-400" />
              </div>
            </div>

            <div>
              <p className="text-sm font-medium text-slate-300">{currentDate || "Loading Date..."}</p>
              <div className="flex items-center space-x-2 mt-3 p-2.5 rounded-lg bg-orange-500/10 border border-orange-500/20">
                <div className="w-2 h-2 rounded-full bg-orange-500 animate-ping" />
                <span className="text-xs font-mono text-orange-300">Fast Pass Auto-Processing Clear</span>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Dynamic Premium Tab Switcher */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="mb-8 p-1.5 rounded-2xl bg-white/40 dark:bg-black/20 border border-gray-200 dark:border-white/5 backdrop-blur-md max-w-2xl"
        >
          <div className="flex flex-wrap md:flex-nowrap gap-1">
            {[
              { id: "overview", label: "Overview", icon: Activity },
              { id: "orders", label: "Active Orders", icon: ShoppingBag },
              { id: "profile", label: "Secure Profile", icon: User }
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
            {/* Main statistics cards grid */}
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
              {[
                {
                  label: "Available Credit",
                  value: `${100 - utilizationPercent}%`,
                  subtext: utilizationPercent === 0 ? "Fully Available" : `${utilizationPercent}% utilized`,
                  icon: TrendingUp,
                  color: "from-emerald-500 to-teal-600",
                  textColor: "text-emerald-500",
                  metric: `${orders.filter((o) => !isDeliveredStatus(o.status) && o.status !== "cancelled").length} active orders`
                },
                {
                  label: "Approved Credit Limit",
                  value: userProfile.creditLimit,
                  subtext: `${100 - utilizationPercent}% Available`,
                  icon: CreditCard,
                  color: "from-orange-500 to-amber-600",
                  textColor: "text-orange-500",
                  metric: userProfile.availableCredit + " available",
                  progress: 100 - utilizationPercent
                },
                {
                  label: "Active Purchases",
                  value: recentOrders.length,
                  subtext: recentOrders.length === 0 ? "No orders yet" : "Orders on file",
                  icon: ShoppingBag,
                  color: "from-sky-500 to-indigo-600",
                  textColor: "text-sky-500",
                  metric: `${orders.filter((o) => !isDeliveredStatus(o.status)).length} in progress`
                },
                {
                  label: "Upcoming Installment",
                  value: upcomingPayments[0]?.amount ?? "—",
                  subtext: upcomingPayments[0]?.order ?? "No pending installments",
                  icon: Calendar,
                  color: "from-pink-500 to-rose-600",
                  textColor: "text-rose-500",
                  metric: upcomingPayments[0] ? `Due in ${upcomingPayments[0].daysLeft} days` : "All caught up"
                }
              ].map((stat, index) => {
                const StatIcon = stat.icon
                return (
                  <motion.div
                    key={stat.label}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, delay: index * 0.08 }}
                  >
                    <Card className="card-surface group hover:-translate-y-1.5 transition-all duration-300 relative overflow-hidden h-full">
                      <CardContent className="p-6 flex flex-col justify-between h-full">
                        <div>
                          <div className="flex items-center justify-between mb-4">
                            <div className={`w-11 h-11 bg-gradient-to-br ${stat.color} rounded-xl flex items-center justify-center shadow-lg shadow-orange-500/5 group-hover:scale-105 transition-transform duration-300`}>
                              <StatIcon className="w-5 h-5 text-white" />
                            </div>
                            <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider font-mono">
                              {stat.metric}
                            </span>
                          </div>
                          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                            {stat.label}
                          </p>
                          <h3 className="text-2xl font-black text-gray-900 dark:text-white tracking-tight">
                            {stat.value}
                          </h3>
                        </div>

                        {/* Additional aesthetic details */}
                        <div className="mt-4 pt-3 border-t border-gray-100 dark:border-white/5">
                          {stat.progress !== undefined ? (
                            <div>
                              <div className="flex justify-between items-center text-[10px] font-mono mb-1 text-gray-400">
                                <span>Limit utilization:</span>
                                <span className="font-bold text-emerald-500">{100 - stat.progress}% Used</span>
                              </div>
                              <div className="w-full h-1.5 bg-gray-100 dark:bg-white/10 rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-gradient-to-r from-emerald-400 to-emerald-500 rounded-full shadow-[0_0_6px_rgba(16,185,129,0.3)]"
                                  style={{ width: `${stat.progress}%` }}
                                />
                              </div>
                            </div>
                          ) : (
                            <span className={`text-xs font-bold ${stat.textColor}`}>{stat.subtext}</span>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                )
              })}
            </div>

            {/* Split Screen: Left Columns Recent Lists, Right Credit Gauge */}
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
                          <p className="text-xs text-gray-500">Overview of active products purchased on installments</p>
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
                          <p className="text-sm text-gray-500 py-4 text-center">No orders yet — head to the Shop to get started.</p>
                        )}
                        {recentOrders.slice(0, 3).map((order) => (
                          <div
                            key={order.id}
                            className="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-gray-50/50 dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/5 hover:border-orange-500/20 hover:bg-orange-500/[0.01] transition-all duration-300 group/item"
                          >
                            <div className="flex items-center space-x-3.5">
                              {getOrderIcon()}
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
                              <div className="flex justify-between items-center text-[10px] font-mono mb-1 text-gray-500">
                                <span>Financing:</span>
                                <span className="font-semibold">
                                  {order.totalInstallments} months
                                </span>
                              </div>
                            </div>

                            <div className="flex items-center justify-between sm:justify-end gap-4 mt-3 sm:mt-0">
                              <div className="text-right">
                                <p className="text-xs text-gray-400">Total Finance</p>
                                <p className="text-sm font-bold text-gray-900 dark:text-white">
                                  {order.amount}
                                </p>
                              </div>
                              <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${getStatusColor(order.rawStatus)}`}>
                                {getStatusIcon(order.rawStatus)}
                                {order.status}
                              </span>
                            </div>
                          </div>
                        ))}
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
                        <p className="text-xs text-gray-500">Pending monthly installments synchronized with Shariah standards</p>
                      </div>

                      <div className="space-y-4">
                        {upcomingPayments.length === 0 && (
                          <p className="text-sm text-gray-500 py-4 text-center">No pending installments — you&apos;re all caught up.</p>
                        )}
                        {upcomingPayments.map((payment, index) => {
                          const isUrgent = payment.daysLeft <= 2
                          return (
                            <div
                              key={index}
                              className="flex items-center justify-between p-4 bg-gray-50/50 dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/5 hover:border-orange-500/20 transition-all duration-300"
                            >
                              <div className="flex items-center space-x-3.5">
                                <div className={`w-10 h-10 rounded-xl flex items-center justify-center border ${
                                  isUrgent
                                    ? "bg-rose-500/10 border-rose-500/20 text-rose-500 animate-pulse"
                                    : "bg-orange-500/10 border-orange-500/20 text-orange-500"
                                }`}>
                                  <Calendar className="w-5 h-5" />
                                </div>
                                <div>
                                  <h4 className="font-bold text-gray-900 dark:text-white text-sm">
                                    {payment.order} Installment
                                  </h4>
                                  <p className="text-xs text-gray-500 mt-0.5">Due Date: {payment.date}</p>
                                </div>
                              </div>

                              <div className="flex items-center space-x-4">
                                <div className="text-right">
                                  <span className={`inline-block px-3 py-1 rounded-full text-[10px] font-bold tracking-wider uppercase ${
                                    isUrgent
                                      ? "text-rose-500 bg-rose-500/10 border border-rose-500/20"
                                      : "text-amber-500 bg-amber-500/10 border border-amber-500/20"
                                  }`}>
                                    {payment.daysLeft} days left
                                  </span>
                                  <p className="text-sm font-bold text-gray-900 dark:text-white mt-1">
                                    {payment.amount}
                                  </p>
                                </div>
                              </div>
                            </div>
                          )
                        })}
                      </div>

                      <Button
                        onClick={() => router.push("/repayment")}
                        className="w-full mt-5 bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white font-bold h-12 rounded-xl shadow-lg shadow-orange-500/10 btn-smooth flex items-center justify-center gap-2"
                      >
                        Make Secure Payment
                        <ArrowRight className="w-4 h-4" />
                      </Button>
                    </CardContent>
                  </Card>
                </motion.div>
              </div>

              {/* Right Column: Credit Score Visualizer */}
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
                        <div className="flex justify-between items-center mb-6">
                          <h3 className="text-lg font-bold text-gray-900 dark:text-white">Credit Health</h3>
                          <span className="px-2.5 py-1 bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 rounded-full text-[10px] font-black uppercase tracking-wider font-mono">
                            Verified Tier 3
                          </span>
                        </div>

                        {/* Interactive Radial Gauge */}
                        <div className="relative flex items-center justify-center my-6">
                          <svg className="w-44 h-44 transform -rotate-90">
                            {/* Static Background circle */}
                            <circle
                              cx="88"
                              cy="88"
                              r={radius}
                              stroke="currentColor"
                              strokeWidth={strokeWidth}
                              className="text-gray-100 dark:text-white/5"
                              fill="transparent"
                            />
                            {/* Glowing Active Arc */}
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
                            {/* Color Gradient definitions */}
                            <defs>
                              <linearGradient id="scoreGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stopColor="#f97316" />
                                <stop offset="60%" stopColor="#ec4899" />
                                <stop offset="100%" stopColor="#10b981" />
                              </linearGradient>
                            </defs>
                          </svg>

                          {/* Inner Telemetry Text */}
                          <div className="absolute flex flex-col items-center justify-center">
                            <motion.span
                              initial={{ scale: 0.6, opacity: 0 }}
                              animate={{ scale: 1, opacity: 1 }}
                              transition={{ duration: 0.8, delay: 0.3 }}
                              className="text-4xl font-black text-gray-900 dark:text-white font-mono tracking-tighter"
                            >
                              {userScore}%
                            </motion.span>
                            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mt-1">
                              Available Credit
                            </span>
                          </div>
                        </div>

                        <div className="p-4 bg-gray-50 dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/5 mt-4">
                          <div className="flex justify-between items-center text-xs mb-2">
                            <span className="text-gray-500">Utilization:</span>
                            <span className="font-extrabold text-emerald-500">
                              {utilizationPercent < 30 ? "Low" : utilizationPercent < 70 ? "Moderate" : "High"}
                            </span>
                          </div>
                          <div className="flex justify-between items-center text-xs">
                            <span className="text-gray-500">Account Status:</span>
                            <span className="font-bold text-gray-900 dark:text-white capitalize">{currentUser?.status ?? "—"}</span>
                          </div>
                        </div>
                      </div>

                      {/* Positives list */}
                      <div className="w-full mt-6 pt-5 border-t border-gray-100 dark:border-white/5 space-y-3 text-left">
                        <div className="flex items-start space-x-2 text-xs">
                          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-1.5 flex-shrink-0" />
                          <p className="text-gray-600 dark:text-gray-400">
                            100% on-time biometric verification scans logged.
                          </p>
                        </div>
                        <div className="flex items-start space-x-2 text-xs">
                          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-1.5 flex-shrink-0" />
                          <p className="text-gray-600 dark:text-gray-400">
                            Zero late installments or payment requests registered.
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
                  <p className="text-xs text-gray-500 mt-1">Detailed list of active Shariah-compliant installment contracts</p>
                </div>

                <div className="space-y-6">
                  {recentOrders.length === 0 && (
                    <p className="text-sm text-gray-500 py-8 text-center">No orders yet — head to the Shop to get started.</p>
                  )}
                  {recentOrders.map((order, index) => (
                    <motion.div
                      key={order.id}
                      initial={{ opacity: 0, y: 15 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.5, delay: index * 0.1 }}
                      className="border border-gray-200 dark:border-white/5 rounded-2xl p-6 hover:shadow-lg dark:hover:bg-white/[0.01] hover:border-orange-500/20 transition-all duration-300 group"
                    >
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 pb-4 border-b border-gray-100 dark:border-white/5">
                        <div className="flex items-center space-x-3.5">
                          {getOrderIcon()}
                          <div>
                            <h4 className="font-extrabold text-gray-900 dark:text-white text-base group-hover:text-orange-500 transition-colors">
                              {order.product}
                            </h4>
                            <p className="text-xs text-gray-500 mt-0.5">Order ID: {order.id}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${getStatusColor(order.rawStatus)}`}>
                            {getStatusIcon(order.rawStatus)}
                            {order.status}
                          </span>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-3 gap-6 text-sm mb-6">
                        <div>
                          <p className="text-[10px] text-gray-500 uppercase tracking-wider font-mono">Finance Value</p>
                          <p className="font-bold text-gray-900 dark:text-white mt-1">{order.amount}</p>
                        </div>
                        <div>
                          <p className="text-[10px] text-gray-500 uppercase tracking-wider font-mono">Order Date</p>
                          <p className="font-bold text-gray-800 dark:text-gray-200 mt-1">{order.date}</p>
                        </div>
                        <div>
                          <p className="text-[10px] text-gray-500 uppercase tracking-wider font-mono">Installment Plan</p>
                          <p className="font-bold text-orange-500 mt-1">{order.totalInstallments} months</p>
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
                          <Download className="w-4 h-4 text-gray-400 group-hover/btn:text-orange-500 transition-colors" />
                          Need Help With This Order
                        </Button>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* Profile Tab Content */}
        {activeTab === "profile" && (
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <div className="grid lg:grid-cols-3 gap-8 items-stretch">
              <motion.div
                initial={{ x: -20, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.1 }}
                className="lg:col-span-2"
              >
                <Card className="card-surface h-full">
                  <CardContent className="p-6 flex flex-col justify-between h-full">
                    <div>
                      <div className="mb-8 border-b border-gray-100 dark:border-white/5 pb-4">
                        <h3 className="text-2xl font-bold text-gray-900 dark:text-white">Profile Credentials</h3>
                        <p className="text-xs text-gray-500 mt-1">Legally authenticated CNIC records & secure telemetry metrics</p>
                      </div>

                      <div className="grid md:grid-cols-2 gap-6">
                        <div className="space-y-1.5">
                          <label className="text-[10px] font-extrabold text-gray-400 uppercase tracking-widest font-mono">
                            Full Legal Name
                          </label>
                          <p className="text-base font-bold text-gray-900 dark:text-white p-3 rounded-xl bg-gray-50 dark:bg-white/5 border border-gray-100 dark:border-white/5">
                            {userProfile.name}
                          </p>
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-[10px] font-extrabold text-gray-400 uppercase tracking-widest font-mono">
                            Email Address
                          </label>
                          <p className="text-base font-bold text-gray-900 dark:text-white p-3 rounded-xl bg-gray-50 dark:bg-white/5 border border-gray-100 dark:border-white/5">
                            {userProfile.email}
                          </p>
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-[10px] font-extrabold text-gray-400 uppercase tracking-widest font-mono">
                            Verified Mobile Node
                          </label>
                          <p className="text-base font-bold text-gray-900 dark:text-white p-3 rounded-xl bg-gray-50 dark:bg-white/5 border border-gray-100 dark:border-white/5">
                            {userProfile.phone}
                          </p>
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-[10px] font-extrabold text-gray-400 uppercase tracking-widest font-mono">
                            CNIC Registry Number
                          </label>
                          <p className="text-base font-bold text-gray-900 dark:text-white p-3 rounded-xl bg-gray-50 dark:bg-white/5 border border-gray-100 dark:border-white/5 font-mono">
                            {userProfile.cnic}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="pt-6 border-t border-gray-100 dark:border-white/5 mt-8 flex flex-wrap gap-3">
                      <Button
                        onClick={() => router.push("/profile")}
                        className="bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white font-bold h-11 px-5 rounded-xl shadow-lg shadow-orange-500/10 btn-smooth"
                      >
                        Update Verified Record
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => router.push("/notifications")}
                        className="h-11 px-5 rounded-xl font-bold border-gray-300 dark:border-white/10 dark:hover:bg-white/5 hover:border-orange-500/30 flex items-center gap-2 group/btn"
                      >
                        <Shield className="w-4 h-4 text-gray-400 group-hover/btn:text-orange-500 transition-colors" />
                        Account Activity
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>

              {/* Secure Pass Column */}
              <motion.div
                initial={{ x: 20, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.2 }}
              >
                <Card className="card-surface p-6 flex flex-col justify-between relative overflow-hidden bg-gradient-to-br from-slate-900 via-slate-950 to-orange-950 border-slate-800 h-full text-white min-h-[400px]">
                  {/* Subtle mesh overlay */}
                  <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-orange-500/15 via-transparent to-transparent opacity-60 pointer-events-none" />

                  {/* Header part */}
                  <div className="relative z-10">
                    <div className="flex justify-between items-start">
                      <div>
                        <span className="text-[9px] font-black tracking-widest text-orange-400 font-mono uppercase bg-orange-500/10 border border-orange-500/20 px-2.5 py-0.5 rounded-full">
                          SahulatKar Digital Identity
                        </span>
                        <h4 className="text-lg font-bold tracking-tight text-white mt-2">
                          Premium Digital Pass
                        </h4>
                      </div>
                      <div className="w-9 h-9 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center">
                        <Cpu className="w-5 h-5 text-orange-400" />
                      </div>
                    </div>

                    {/* Golden Contact Microchip */}
                    <div className="w-12 h-9 rounded-lg bg-gradient-to-r from-amber-400 via-yellow-300 to-amber-500 border border-amber-600/30 shadow-md relative overflow-hidden mt-6 flex items-center justify-center">
                      <div className="absolute inset-0 grid grid-cols-3 gap-px opacity-30">
                        <div className="border-r border-b border-black/20" />
                        <div className="border-r border-b border-black/20" />
                        <div className="border-b border-black/20" />
                        <div className="border-r border-b border-black/20" />
                        <div className="border-r border-b border-black/20" />
                        <div className="border-b border-black/20" />
                      </div>
                      <Cpu className="w-5 h-5 text-amber-900/60" />
                    </div>
                  </div>

                  {/* Middle part */}
                  <div className="relative z-10 my-6">
                    <p className="text-[10px] font-mono tracking-widest text-slate-400 uppercase">
                      Pass Holder Name
                    </p>
                    <p className="text-lg font-black tracking-wide text-white font-sans mt-0.5">
                      {userProfile.name}
                    </p>
                    <div className="grid grid-cols-2 gap-4 mt-4">
                      <div>
                        <p className="text-[9px] font-mono text-slate-400 uppercase tracking-wider">CNIC NODE</p>
                        <p className="text-sm font-bold tracking-wide font-mono text-slate-200 mt-0.5">
                          {userProfile.cnic.replace(/-.*/, " - ••••••• - 3")}
                        </p>
                      </div>
                      <div>
                        <p className="text-[9px] font-mono text-slate-400 uppercase tracking-wider">MEMBER SINCE</p>
                        <p className="text-sm font-bold tracking-wide font-mono text-slate-200 mt-0.5">
                          01 / 2024
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Footer part with QR code */}
                  <div className="relative z-10 pt-4 border-t border-white/5 flex items-center justify-between">
                    <div>
                      <p className="text-[10px] font-mono text-orange-400 font-bold uppercase tracking-wider">
                        PLATINUM LEVEL MEMBER
                      </p>
                      <p className="text-xs text-slate-400 font-mono mt-0.5">
                        Credit Band Limit: 500k
                      </p>
                    </div>
                    <div className="w-14 h-14 bg-white p-1 rounded-lg shadow-lg relative overflow-hidden group/qr">
                      <div className="absolute inset-0 bg-gradient-to-br from-amber-400/20 to-orange-500/20 opacity-0 group-hover/qr:opacity-100 transition-opacity duration-300 pointer-events-none" />
                      <QrCode className="w-full h-full text-slate-900" />
                    </div>
                  </div>
                </Card>
              </motion.div>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  )
}

