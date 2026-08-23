"use client"

import { motion, AnimatePresence } from "framer-motion"
import { useEffect, useRef, useState } from "react"
import { Trash2, Plus, ShoppingBag, ArrowRight, Shield, Truck, Link2, Loader2, AlertCircle, CheckCircle2, ReceiptText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { ProgressTimeline, type TimelineStep } from "@/components/ui/progress-timeline"
import { SkeletonProductCard } from "@/components/ui/skeleton"
import { useRouter } from "next/navigation"
import { cartApi, type CartItemView } from "@/lib/cart-api"
import { ApiError } from "@/lib/api-client"
import { formatCurrency } from "@/lib/utils"

const INSTALLMENT_OPTIONS = [3, 4, 6, 12] as const

const ITEM_STEPS: TimelineStep[] = [
  { key: "paste", label: "Pasted" },
  { key: "analyze", label: "Checking eligibility" },
  { key: "priced", label: "Priced & financed" },
]

const EXAMPLE_RETAILERS = ["Daraz", "Amazon.pk", "Telemart", "iShopping"]

function NewPurchaseSkeleton() {
  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto px-4 max-w-6xl animate-pulse">
        <div className="card-surface h-10 w-64 rounded-xl mb-3" />
        <div className="card-surface h-5 w-96 rounded-lg mb-8" />
        <div className="card-surface h-24 rounded-2xl mb-8" />
        <div className="grid lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 card-surface h-64 rounded-2xl" />
          <div className="card-surface h-96 rounded-2xl" />
        </div>
      </div>
    </div>
  )
}

export default function NewPurchase() {
  const router = useRouter()
  const [items, setItems] = useState<CartItemView[]>([])
  const [loaded, setLoaded] = useState(false)
  const [productUrl, setProductUrl] = useState("")
  const [isAdding, setIsAdding] = useState(false)
  const [addError, setAddError] = useState("")
  const [installmentCount, setInstallmentCount] = useState<typeof INSTALLMENT_OPTIONS[number]>(4)
  const [isCheckingOut, setIsCheckingOut] = useState(false)
  const [checkoutError, setCheckoutError] = useState("")
  const pollRef = useRef<number | null>(null)

  const refreshCart = async () => {
    const cart = await cartApi.getCart()
    setItems(cart.items)
    setLoaded(true)
    return cart.items
  }

  useEffect(() => {
    // Auth is enforced server-side by middleware.ts before this page ever
    // renders; the initial cart fetch requires a network call, which can
    // only happen in an effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshCart().catch(() => setLoaded(true))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const hasPending = items.some((item) => item.offer.status === "pending")
    if (!hasPending) return
    pollRef.current = window.setTimeout(() => {
      refreshCart().catch(() => {})
    }, 2500)
    return () => {
      if (pollRef.current) window.clearTimeout(pollRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items])

  const handleAddItem = async () => {
    if (!productUrl.trim()) return
    setIsAdding(true)
    setAddError("")
    try {
      await cartApi.addItem(productUrl.trim())
      setProductUrl("")
      await refreshCart()
    } catch (err) {
      const detail = err instanceof ApiError ? String(err.detail) : "Could not add this product. Please try again."
      const friendly: Record<string, string> = {
        KYC_NOT_APPROVED: "Your identity verification isn't approved yet.",
        NO_CREDIT_AVAILABLE: "You don't have available credit right now.",
        TOO_MANY_ACTIVE_ORDERS: "You have too many active orders — complete or cancel one first.",
      }
      setAddError(friendly[detail] ?? detail)
    } finally {
      setIsAdding(false)
    }
  }

  const handleRemoveItem = async (cartItemId: number) => {
    try {
      await cartApi.removeItem(cartItemId)
      await refreshCart()
    } catch {
      setAddError("Could not remove this item.")
    }
  }

  const readyItems = items.filter((item) => item.offer.status === "ready")
  const pendingCount = items.filter((item) => item.offer.status === "pending").length
  const subtotal = readyItems.reduce((sum, item) => sum + (item.offer.product?.price ?? 0), 0)
  const downPaymentPct = readyItems[0]?.offer.financing?.down_payment_pct ?? 25
  const estimatedDownPayment = readyItems.reduce((sum, item) => {
    const pct = item.offer.financing?.down_payment_pct ?? 25
    return sum + (item.offer.product?.price ?? 0) * (pct / 100)
  }, 0)
  const financedAmount = Math.max(subtotal - estimatedDownPayment, 0)

  // Every tenure the first ready item's offer supports, priced out so the customer
  // can compare the true monthly amount and total cost before choosing — not just a bare "4mo" label.
  const planOptions = INSTALLMENT_OPTIONS.map((count) => {
    const plan = readyItems[0]?.offer.financing?.plans.find((p) => p.installment_count === count)
    if (!plan || subtotal === 0) return { count, available: false, monthly: 0, profit: 0 }
    const totalWithProfit = financedAmount * (1 + plan.profit_rate_pct / 100)
    return {
      count,
      available: true,
      monthly: Math.round(totalWithProfit / count),
      profit: Math.round(totalWithProfit - financedAmount),
      profitRatePct: plan.profit_rate_pct,
    }
  })
  const selectedPlan = planOptions.find((p) => p.count === installmentCount)

  const allReady = items.length > 0 && items.every((item) => item.offer.status === "ready")

  const handleCheckout = async () => {
    setIsCheckingOut(true)
    setCheckoutError("")
    try {
      const result = await cartApi.checkout(installmentCount)
      sessionStorage.setItem("sk_cart_order_ids", JSON.stringify(result.order_ids))
      sessionStorage.setItem("sk_cart_installment_count", String(result.installment_count))
      router.push("/financing/wakalaah-agreement")
    } catch (err) {
      const message = err instanceof ApiError ? String(err.detail) : "Could not start checkout. Please try again."
      setCheckoutError(message)
      setIsCheckingOut(false)
    }
  }

  if (!loaded) return <NewPurchaseSkeleton />

  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto px-4 max-w-6xl">
        <motion.div
          initial={{ y: -20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6 }}
          className="mb-8"
        >
          <h1 className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight mb-1.5">New Purchase</h1>
          <p className="text-gray-600 dark:text-gray-400">
            Paste a product link from any online store — we&apos;ll check the price, confirm it&apos;s in stock, and give you a financing offer in seconds.
          </p>
        </motion.div>

        <Card className="card-surface mb-8">
          <CardContent className="p-6">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <Link2 className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  value={productUrl}
                  onChange={(e) => setProductUrl(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddItem()}
                  placeholder="https://www.daraz.pk/products/..."
                  className="pl-11 h-14 rounded-xl"
                />
              </div>
              <Button
                onClick={handleAddItem}
                disabled={isAdding || !productUrl.trim()}
                className="h-14 rounded-xl font-bold px-6 bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 shadow-lg shadow-orange-500/10 btn-smooth"
              >
                {isAdding ? <Loader2 className="w-5 h-5 animate-spin" /> : <Plus className="w-5 h-5 mr-1" />}
                Add Item
              </Button>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-500">
              <span>Works with</span>
              {EXAMPLE_RETAILERS.map((name, i) => (
                <span key={name} className="font-semibold text-gray-600 dark:text-gray-300">
                  {name}{i < EXAMPLE_RETAILERS.length - 1 ? "," : ", and most Pakistani retailers"}
                </span>
              ))}
            </div>
            {addError && (
              <div className="mt-3 flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                <AlertCircle className="w-4 h-4 flex-none" /> {addError}
              </div>
            )}
          </CardContent>
        </Card>

        {items.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5 }}
            className="text-center py-20"
          >
            <div className="w-24 h-24 rounded-full flex items-center justify-center mx-auto mb-6 bg-orange-500/10">
              <ShoppingBag className="w-11 h-11 text-orange-500" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">Nothing added yet</h2>
            <p className="text-gray-500 max-w-sm mx-auto">
              Paste a product link above and we&apos;ll take care of pricing, eligibility, and a repayment plan.
            </p>
          </motion.div>
        ) : (
          <div className="grid lg:grid-cols-3 gap-8">
            <motion.div
              initial={{ x: -30, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.15 }}
              className="lg:col-span-2"
            >
              <div className="space-y-4">
                <AnimatePresence>
                  {items.map((item, index) => (
                    <motion.div
                      key={item.cart_item_id}
                      layout
                      initial={{ opacity: 0, x: -30 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 30 }}
                      transition={{ duration: 0.3, delay: index * 0.08 }}
                    >
                      <Card className="card-surface">
                        <CardContent className="p-6">
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex-1 min-w-0">
                              {item.offer.status === "pending" && (
                                <div className="space-y-4">
                                  <ProgressTimeline steps={ITEM_STEPS} activeIndex={1} className="max-w-xs" />
                                  <SkeletonProductCard />
                                </div>
                              )}
                              <AnimatePresence mode="wait">
                                {item.offer.status === "ready" && item.offer.product && (
                                  <motion.div
                                    key="ready"
                                    initial={{ opacity: 0, y: 8 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ duration: 0.4, ease: "easeOut" }}
                                  >
                                    <ProgressTimeline steps={ITEM_STEPS} activeIndex={3} className="mb-4 max-w-xs" />
                                    <div className="flex items-start gap-3">
                                      {item.offer.product.image_url && (
                                        // eslint-disable-next-line @next/next/no-img-element
                                        <img
                                          src={item.offer.product.image_url}
                                          alt={item.offer.product.name}
                                          className="h-16 w-16 shrink-0 rounded-lg border border-gray-100 dark:border-white/10 object-cover"
                                        />
                                      )}
                                      <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-2">
                                          <h3 className="font-bold text-gray-900 dark:text-white truncate">{item.offer.product.name}</h3>
                                          <motion.span
                                            initial={{ scale: 0, opacity: 0 }}
                                            animate={{ scale: 1, opacity: 1 }}
                                            transition={{ delay: 0.2, type: "spring", stiffness: 400, damping: 15 }}
                                            className="flex-none"
                                          >
                                            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                                          </motion.span>
                                        </div>
                                        {item.offer.product.brand && (
                                          <p className="text-xs text-gray-500">{item.offer.product.brand}</p>
                                        )}
                                        <p className="text-sm text-gray-500 truncate max-w-md">{item.offer.product.url}</p>
                                        {item.offer.product.availability && (
                                          <span
                                            className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                                              item.offer.product.availability === "in_stock"
                                                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                                : item.offer.product.availability === "out_of_stock"
                                                ? "bg-red-500/10 text-red-600 dark:text-red-400"
                                                : "bg-gray-500/10 text-gray-500"
                                            }`}
                                          >
                                            {item.offer.product.availability.replace(/_/g, " ")}
                                          </span>
                                        )}
                                        {item.offer.product.variants && item.offer.product.variants.length > 0 && (
                                          <div className="mt-2 space-y-1.5">
                                            {item.offer.product.variants.map((variant) => (
                                              <div key={variant.option_name} className="flex flex-wrap items-center gap-1.5">
                                                <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                                                  {variant.option_name}:
                                                </span>
                                                {variant.options.map((opt) => (
                                                  <span
                                                    key={opt.value}
                                                    className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                                                      opt.is_available === false
                                                        ? "border-gray-200 dark:border-white/10 text-gray-400 line-through"
                                                        : "border-orange-500/30 text-gray-700 dark:text-gray-200"
                                                    }`}
                                                  >
                                                    {opt.label}
                                                  </span>
                                                ))}
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                    <div className="mt-3 flex items-center justify-between">
                                      <span className="text-lg font-bold text-gray-900 dark:text-white tabular-nums">
                                        {formatCurrency(item.offer.product.price)}
                                      </span>
                                      {item.offer.financing && (
                                        <span className="text-sm text-emerald-600 dark:text-emerald-400 font-medium">
                                          {item.offer.financing.down_payment_pct}% down payment
                                        </span>
                                      )}
                                    </div>
                                  </motion.div>
                                )}
                              </AnimatePresence>
                              {(item.offer.status === "extraction_failed" || item.offer.status === "declined") && (
                                <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
                                  <AlertCircle className="w-5 h-5 flex-none" />
                                  <span className="text-sm">{item.offer.reason ?? "This product couldn't be added."}</span>
                                </div>
                              )}
                            </div>
                            <button
                              type="button"
                              aria-label="Remove item"
                              onClick={() => handleRemoveItem(item.cart_item_id)}
                              className="text-gray-400 transition-colors hover:text-red-500 flex-none"
                            >
                              <Trash2 className="w-5 h-5" />
                            </button>
                          </div>
                        </CardContent>
                      </Card>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            </motion.div>

            <motion.div
              initial={{ x: 30, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.25 }}
              className="lg:col-span-1"
            >
              <div className="sticky top-24">
                <Card className="card-surface">
                  <CardContent className="p-6">
                    <div className="flex items-center gap-2 mb-5">
                      <ReceiptText className="w-5 h-5 text-orange-500" />
                      <h3 className="text-lg font-bold text-gray-900 dark:text-white">Financing Summary</h3>
                    </div>

                    {subtotal === 0 ? (
                      <p className="text-sm text-gray-500 py-2">
                        {pendingCount > 0 ? "Pricing your item…" : "Add an item to see your plan."}
                      </p>
                    ) : (
                      <>
                        <div className="space-y-3 mb-5 text-sm">
                          <div className="flex justify-between">
                            <span className="text-gray-500">Subtotal ({readyItems.length} ready)</span>
                            <span className="font-semibold text-gray-900 dark:text-white tabular-nums">{formatCurrency(subtotal)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-500">Due today (~{downPaymentPct}%)</span>
                            <span className="font-semibold text-gray-900 dark:text-white tabular-nums">{formatCurrency(Math.round(estimatedDownPayment))}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-500">Financed amount</span>
                            <span className="font-semibold text-gray-900 dark:text-white tabular-nums">{formatCurrency(Math.round(financedAmount))}</span>
                          </div>
                        </div>

                        <div className="rounded-xl border border-gray-100 dark:border-white/10 p-4 mb-5">
                          <h4 className="font-semibold text-gray-900 dark:text-white mb-3 text-sm">Choose your repayment term</h4>
                          <div className="grid grid-cols-2 gap-2 mb-3">
                            {planOptions.map((plan) => (
                              <button
                                key={plan.count}
                                type="button"
                                disabled={!plan.available}
                                onClick={() => setInstallmentCount(plan.count)}
                                className={`rounded-xl border p-3 text-left transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                                  installmentCount === plan.count
                                    ? "border-orange-500 bg-orange-500/10"
                                    : "border-gray-200 dark:border-white/10 hover:border-orange-500/30"
                                }`}
                              >
                                <p className="text-xs font-bold text-gray-500 uppercase tracking-wide">{plan.count} months</p>
                                <p className="text-sm font-extrabold text-gray-900 dark:text-white tabular-nums mt-0.5">
                                  {plan.available ? `${formatCurrency(plan.monthly)}/mo` : "—"}
                                </p>
                              </button>
                            ))}
                          </div>
                          {selectedPlan?.available && (
                            <p className="text-xs text-gray-500">
                              Total profit over {selectedPlan.count} months: <span className="font-semibold text-gray-700 dark:text-gray-300">{formatCurrency(selectedPlan.profit)}</span> ({selectedPlan.profitRatePct}%, fixed and disclosed upfront — never compounding).
                            </p>
                          )}
                        </div>
                      </>
                    )}

                    <div className="space-y-3 mb-6 text-sm">
                      <div className="flex items-center gap-3">
                        <Shield className="w-4.5 h-4.5 text-emerald-500 flex-none" />
                        <span className="text-gray-700 dark:text-gray-300">Shariah-compliant, interest-free structure</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <Truck className="w-4.5 h-4.5 text-sky-500 flex-none" />
                        <span className="text-gray-700 dark:text-gray-300">Delivered straight from the retailer</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <ReceiptText className="w-4.5 h-4.5 text-purple-500 flex-none" />
                        <span className="text-gray-700 dark:text-gray-300">One combined schedule for every item</span>
                      </div>
                    </div>

                    {checkoutError && (
                      <div className="mb-4 flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                        <AlertCircle className="w-4 h-4 flex-none" /> {checkoutError}
                      </div>
                    )}

                    <Button
                      disabled={!allReady || isCheckingOut}
                      onClick={handleCheckout}
                      className="w-full h-14 rounded-xl font-bold bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 shadow-lg shadow-orange-500/10 btn-smooth flex items-center justify-center gap-2 disabled:opacity-50"
                    >
                      {isCheckingOut ? "Starting checkout…" : "Continue to Financing"}
                      <ArrowRight className="w-5 h-5" />
                    </Button>
                    {!allReady && items.length > 0 && (
                      <p className="text-xs text-gray-500 text-center mt-3">
                        Waiting for every item to finish pricing before checkout.
                      </p>
                    )}
                  </CardContent>
                </Card>
              </div>
            </motion.div>
          </div>
        )}
      </div>
    </div>
  )
}
