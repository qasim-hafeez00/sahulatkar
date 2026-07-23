"use client"

import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { AlertCircle, CreditCard, Plus, Smartphone, Star, Trash2, Banknote } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { ApiError } from "@/lib/api-client"
import { paymentMethodsApi, type PaymentProvider, type SavedPaymentMethod } from "@/lib/payment-methods-api"

const PROVIDERS: { id: PaymentProvider; label: string; type: "wallet" | "card"; icon: typeof Banknote }[] = [
  { id: "jazzcash", label: "JazzCash", type: "wallet", icon: Smartphone },
  { id: "easypaisa", label: "EasyPaisa", type: "wallet", icon: Smartphone },
  { id: "raast", label: "Raast", type: "wallet", icon: Banknote },
  { id: "card", label: "Debit / Credit Card", type: "card", icon: CreditCard },
]

export default function PaymentMethodsPage() {
  const [methods, setMethods] = useState<SavedPaymentMethod[]>([])
  const [provider, setProvider] = useState<PaymentProvider>("jazzcash")
  const [identifier, setIdentifier] = useState("")
  const [expiryMonth, setExpiryMonth] = useState("")
  const [expiryYear, setExpiryYear] = useState("")
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    // Auth is enforced server-side by middleware.ts before this page ever renders.
    load()
  }, [])

  const load = () => {
    paymentMethodsApi.list().then(setMethods).finally(() => setLoaded(true))
  }

  const selectedProvider = PROVIDERS.find((p) => p.id === provider)!

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setIsSubmitting(true)
    try {
      await paymentMethodsApi.add({
        provider,
        method_type: selectedProvider.type === "card" ? "card" : "wallet",
        account_identifier: identifier,
        expiry_month: selectedProvider.type === "card" ? expiryMonth : undefined,
        expiry_year: selectedProvider.type === "card" ? expiryYear : undefined,
      })
      setIdentifier("")
      setExpiryMonth("")
      setExpiryYear("")
      setShowForm(false)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not add this payment method.")
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleRemove = async (id: number) => {
    try {
      await paymentMethodsApi.remove(id)
      load()
    } catch {
      // non-critical
    }
  }

  const handleSetDefault = async (id: number) => {
    try {
      await paymentMethodsApi.setDefault(id)
      load()
    } catch {
      // non-critical
    }
  }

  if (!loaded) return null

  return (
    <div className="min-h-screen pt-28 pb-16">
      <div className="container mx-auto max-w-2xl px-4">
        <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.6 }} className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Payment Methods</h1>
            <p className="text-gray-600 dark:text-gray-400">Manage the wallets and cards used for down payments and installments</p>
          </div>
          <Button onClick={() => setShowForm((v) => !v)} className="bg-gradient-to-r from-orange-500 to-orange-600">
            <Plus className="w-4 h-4 mr-1" /> Add
          </Button>
        </motion.div>

        {showForm && (
          <Card className="border-0 shadow-large mb-6">
            <CardContent className="p-6">
              <form onSubmit={handleAdd} className="space-y-4">
                <div className="grid grid-cols-4 gap-3">
                  {PROVIDERS.map((p) => (
                    <button
                      type="button"
                      key={p.id}
                      onClick={() => setProvider(p.id)}
                      className={`p-3 rounded-xl border-2 text-center transition-all ${
                        provider === p.id ? "border-orange-500 bg-orange-50 dark:bg-orange-500/10" : "border-gray-200 dark:border-white/10"
                      }`}
                    >
                      <p.icon className="w-5 h-5 mx-auto mb-1 text-orange-500" />
                      <span className="text-xs font-semibold">{p.label}</span>
                    </button>
                  ))}
                </div>

                <Input
                  placeholder={selectedProvider.type === "card" ? "Card number (e.g. 4242424242424242)" : "Mobile wallet number (e.g. 03001234567)"}
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4"
                  required
                />

                {selectedProvider.type === "card" && (
                  <div className="grid grid-cols-2 gap-3">
                    <Input
                      placeholder="MM"
                      value={expiryMonth}
                      onChange={(e) => setExpiryMonth(e.target.value)}
                      className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4"
                      required
                    />
                    <Input
                      placeholder="YYYY"
                      value={expiryYear}
                      onChange={(e) => setExpiryYear(e.target.value)}
                      className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4"
                      required
                    />
                  </div>
                )}

                {error && (
                  <div className="flex items-center gap-2 text-sm text-red-600">
                    <AlertCircle className="w-4 h-4" /> {error}
                  </div>
                )}

                <Button type="submit" disabled={isSubmitting || !identifier} className="w-full bg-gradient-to-r from-orange-500 to-orange-600 disabled:opacity-60">
                  {isSubmitting ? "Adding..." : "Save Payment Method"}
                </Button>
              </form>
            </CardContent>
          </Card>
        )}

        {methods.length === 0 ? (
          <Card className="border-0 shadow-large">
            <CardContent className="p-12 text-center text-gray-500">
              No saved payment methods yet.
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {methods.map((m) => (
              <Card key={m.id} className="border-0 shadow-sm">
                <CardContent className="p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center">
                      {m.method_type === "card" ? <CreditCard className="w-5 h-5 text-orange-500" /> : <Smartphone className="w-5 h-5 text-orange-500" />}
                    </div>
                    <div>
                      <p className="font-semibold text-sm text-gray-900 dark:text-white capitalize">{m.provider}</p>
                      <p className="text-xs text-gray-500 font-mono">
                        {m.masked_pan}
                        {m.expiry_month && m.expiry_year ? ` • Exp ${m.expiry_month}/${m.expiry_year}` : ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {m.is_default ? (
                      <span className="flex items-center gap-1 text-xs font-semibold text-orange-600 bg-orange-500/10 px-2.5 py-1 rounded-full">
                        <Star className="w-3 h-3 fill-orange-500" /> Default
                      </span>
                    ) : (
                      <button onClick={() => handleSetDefault(m.id)} className="text-xs font-semibold text-gray-500 hover:text-orange-500">
                        Set default
                      </button>
                    )}
                    <button onClick={() => handleRemove(m.id)} className="text-gray-400 hover:text-red-500 p-1.5">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
