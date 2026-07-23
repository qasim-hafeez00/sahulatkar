"use client"

import { motion, AnimatePresence } from "framer-motion"
import { useEffect, useRef, useState } from "react"
import { Trash2, Plus, ShoppingBag, ArrowRight, Shield, CreditCard, Truck, Link2, Loader2, AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { useRouter } from "next/navigation"
import { cartApi, type CartItemView } from "@/lib/cart-api"
import { ApiError } from "@/lib/api-client"

const INSTALLMENT_OPTIONS = [3, 4, 6, 12] as const

export default function Cart() {
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
    // renders; no client-side redirect-on-missing-token needed here anymore.
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
  const subtotal = readyItems.reduce((sum, item) => sum + (item.offer.product?.price ?? 0), 0)
  const downPaymentPct = readyItems[0]?.offer.financing?.down_payment_pct ?? 25
  const estimatedDownPayment = readyItems.reduce((sum, item) => {
    const pct = item.offer.financing?.down_payment_pct ?? 25
    return sum + (item.offer.product?.price ?? 0) * (pct / 100)
  }, 0)
  const plan = readyItems[0]?.offer.financing?.plans.find((p) => p.installment_count === installmentCount)
  const monthlyEstimate = subtotal > 0 && plan
    ? ((subtotal - estimatedDownPayment) * (1 + plan.profit_rate_pct / 100)) / installmentCount
    : 0

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
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Universal Cart</h1>
          <p className="text-gray-600">Paste a product URL from any store — we'll extract it and finance the whole cart together</p>
        </motion.div>

        <Card className="border-0 shadow-medium mb-8">
          <CardContent className="p-6">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <Link2 className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  value={productUrl}
                  onChange={(e) => setProductUrl(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddItem()}
                  placeholder="https://www.daraz.pk/products/..."
                  className="pl-10 py-6"
                />
              </div>
              <Button
                onClick={handleAddItem}
                disabled={isAdding || !productUrl.trim()}
                className="bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 py-6 px-8"
              >
                {isAdding ? <Loader2 className="w-5 h-5 animate-spin" /> : <Plus className="w-5 h-5 mr-2" />}
                Add to Cart
              </Button>
            </div>
            {addError && (
              <div className="mt-3 flex items-center gap-2 text-sm text-red-600">
                <AlertCircle className="w-4 h-4" /> {addError}
              </div>
            )}
          </CardContent>
        </Card>

        {items.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6 }}
            className="text-center py-20"
          >
            <div className="w-32 h-32 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-6">
              <ShoppingBag className="w-16 h-16 text-gray-400" />
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-4">Your cart is empty</h2>
            <p className="text-gray-600">Paste a product URL above to get started</p>
          </motion.div>
        ) : (
          <div className="grid lg:grid-cols-3 gap-8">
            <motion.div
              initial={{ x: -50, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="lg:col-span-2"
            >
              <div className="space-y-4">
                <AnimatePresence>
                  {items.map((item, index) => (
                    <motion.div
                      key={item.cart_item_id}
                      initial={{ opacity: 0, x: -50 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 50 }}
                      transition={{ duration: 0.3, delay: index * 0.1 }}
                    >
                      <Card className="border-0 shadow-medium hover:shadow-large transition-all duration-300">
                        <CardContent className="p-6">
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex-1">
                              {item.offer.status === "pending" && (
                                <div className="flex items-center gap-3 text-gray-600">
                                  <Loader2 className="w-5 h-5 animate-spin text-orange-500" />
                                  <span>Extracting product details...</span>
                                </div>
                              )}
                              {item.offer.status === "ready" && item.offer.product && (
                                <>
                                  <h3 className="font-semibold text-gray-900 mb-1">{item.offer.product.name}</h3>
                                  <p className="text-sm text-gray-500 truncate max-w-md">{item.offer.product.url}</p>
                                  <div className="mt-3 flex items-center justify-between">
                                    <span className="text-lg font-bold text-gray-900">
                                      PKR {item.offer.product.price.toLocaleString()}
                                    </span>
                                    {item.offer.financing && (
                                      <span className="text-sm text-green-600">
                                        {item.offer.financing.down_payment_pct}% down payment
                                      </span>
                                    )}
                                  </div>
                                </>
                              )}
                              {(item.offer.status === "extraction_failed" || item.offer.status === "declined") && (
                                <div className="flex items-center gap-2 text-red-600">
                                  <AlertCircle className="w-5 h-5" />
                                  <span>{item.offer.reason ?? "This product couldn't be added."}</span>
                                </div>
                              )}
                            </div>
                            <button
                              type="button"
                              aria-label="Remove item"
                              onClick={() => handleRemoveItem(item.cart_item_id)}
                              className="text-gray-400 hover:text-red-500 transition-colors"
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
              initial={{ x: 50, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.4 }}
              className="lg:col-span-1"
            >
              <div className="sticky top-24">
                <Card className="border-0 shadow-large">
                  <CardContent className="p-6">
                    <h3 className="text-xl font-bold text-gray-900 mb-6">Order Summary</h3>

                    <div className="space-y-4 mb-6">
                      <div className="flex justify-between">
                        <span className="text-gray-600">Subtotal ({readyItems.length} ready)</span>
                        <span className="font-semibold">PKR {subtotal.toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">Down Payment (~{downPaymentPct}%)</span>
                        <span className="font-semibold">PKR {Math.round(estimatedDownPayment).toLocaleString()}</span>
                      </div>
                      <div className="border-t pt-4">
                        <div className="flex justify-between text-lg">
                          <span className="font-bold">Total</span>
                          <span className="font-bold text-orange-600">PKR {subtotal.toLocaleString()}</span>
                        </div>
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-orange-50 to-orange-100 rounded-xl p-4 mb-6">
                      <h4 className="font-semibold text-gray-900 mb-3">Unified Financing Plan</h4>
                      <div className="grid grid-cols-4 gap-2 mb-3">
                        {INSTALLMENT_OPTIONS.map((count) => (
                          <button
                            key={count}
                            type="button"
                            onClick={() => setInstallmentCount(count)}
                            className={`rounded-lg py-2 text-xs font-bold transition ${
                              installmentCount === count
                                ? "bg-orange-500 text-white"
                                : "bg-white text-gray-600 border border-gray-200"
                            }`}
                          >
                            {count}mo
                          </button>
                        ))}
                      </div>
                      <div className="space-y-2">
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-600">Est. Monthly Payment</span>
                          <span className="font-semibold text-orange-600">
                            PKR {Math.round(monthlyEstimate).toLocaleString()}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3 mb-6">
                      <div className="flex items-center space-x-3 text-sm">
                        <Shield className="w-5 h-5 text-green-600" />
                        <span className="text-gray-700">Shariah Compliant</span>
                      </div>
                      <div className="flex items-center space-x-3 text-sm">
                        <Truck className="w-5 h-5 text-blue-600" />
                        <span className="text-gray-700">Free Delivery</span>
                      </div>
                      <div className="flex items-center space-x-3 text-sm">
                        <CreditCard className="w-5 h-5 text-purple-600" />
                        <span className="text-gray-700">One combined repayment schedule</span>
                      </div>
                    </div>

                    {checkoutError && (
                      <div className="mb-4 flex items-center gap-2 text-sm text-red-600">
                        <AlertCircle className="w-4 h-4" /> {checkoutError}
                      </div>
                    )}

                    <Button
                      size="xl"
                      disabled={!allReady || isCheckingOut}
                      onClick={handleCheckout}
                      className="w-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 shadow-lg disabled:opacity-50"
                    >
                      {isCheckingOut ? "Starting checkout..." : "Proceed to Financing"}
                      <ArrowRight className="w-5 h-5 ml-2" />
                    </Button>
                    {!allReady && items.length > 0 && (
                      <p className="text-xs text-gray-500 text-center mt-3">
                        Waiting for all items to finish extraction before checkout.
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
