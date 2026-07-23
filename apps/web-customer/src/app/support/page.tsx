"use client"

import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { LifeBuoy, Mail, MessageCircle, Phone, ChevronDown, AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { ApiError } from "@/lib/api-client"
import { supportApi, type TicketCategory, type TicketSummary } from "@/lib/support-api"

const CATEGORY_OPTIONS: { id: TicketCategory; label: string }[] = [
  { id: "general", label: "General Question" },
  { id: "account_issue", label: "Account Issue" },
  { id: "kyc_query", label: "KYC / Verification" },
  { id: "contract_query", label: "Financing Contract" },
  { id: "product_issue", label: "Product Issue" },
]

const FAQS = [
  { q: "How does Shariah-compliant financing work?", a: "SahulatKar uses a Murabaha (cost-plus-profit sale) structure preceded by a Wakalah (agency) agreement so we can purchase the product on your behalf, then sell it to you at a fixed, disclosed profit — no interest is ever charged." },
  { q: "How do I check my payment schedule?", a: "Visit the Repayment Center from the navigation menu to see all upcoming and past installments across your active financing." },
  { q: "What happens if I miss an installment?", a: "Contact support as soon as possible. Late fees may apply per your signed Murabaha contract, and repeated missed payments can affect your credit limit." },
  { q: "Can I return a product I financed?", a: "Use the Dispute & Refunds page to submit a refund request for an eligible order. Our team will review it and respond via your ticket." },
]

export default function SupportPage() {
  const router = useRouter()
  const [category, setCategory] = useState<TicketCategory>("general")
  const [subject, setSubject] = useState("")
  const [description, setDescription] = useState("")
  const [tickets, setTickets] = useState<TicketSummary[]>([])
  const [openFaq, setOpenFaq] = useState<number | null>(null)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    // Auth is enforced server-side by middleware.ts before this page ever renders.
    loadTickets()
  }, [])

  const loadTickets = () => {
    supportApi.list().then(setTickets).finally(() => setLoaded(true))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setSuccess("")
    setIsSubmitting(true)
    try {
      const ticket = await supportApi.create({ category, subject, description })
      setSuccess(`Ticket ${ticket.ticket_number} created. Our team will respond soon.`)
      setSubject("")
      setDescription("")
      loadTickets()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not submit your request. Please try again.")
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!loaded) return null

  return (
    <div className="min-h-screen pt-28 pb-16">
      <div className="container mx-auto max-w-5xl px-4">
        <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.6 }} className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Help & Support</h1>
          <p className="text-gray-600 dark:text-gray-400">Find answers or reach out to our support team</p>
          <div className="mt-4 flex flex-wrap gap-4 text-sm text-gray-500 dark:text-gray-400">
            <span className="flex items-center gap-2"><Phone className="w-4 h-4 text-orange-500" /> 0800-SAHULAT</span>
            <span className="flex items-center gap-2"><Mail className="w-4 h-4 text-orange-500" /> support@sahulatkar.pk</span>
            <span className="flex items-center gap-2"><LifeBuoy className="w-4 h-4 text-orange-500" /> Need a refund? <button onClick={() => router.push("/support/dispute")} className="font-semibold text-orange-500 hover:underline">Dispute & Refunds</button></span>
          </div>
        </motion.div>

        <div className="grid lg:grid-cols-2 gap-8">
          <div className="space-y-4">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">Frequently Asked Questions</h2>
            {FAQS.map((faq, i) => (
              <Card key={i} className="border-0 shadow-sm">
                <CardContent className="p-0">
                  <button
                    className="w-full flex items-center justify-between p-4 text-left"
                    onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  >
                    <span className="font-semibold text-gray-900 dark:text-white text-sm">{faq.q}</span>
                    <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${openFaq === i ? "rotate-180" : ""}`} />
                  </button>
                  {openFaq === i && (
                    <p className="px-4 pb-4 text-sm text-gray-600 dark:text-gray-400">{faq.a}</p>
                  )}
                </CardContent>
              </Card>
            ))}

            <h2 className="text-xl font-bold text-gray-900 dark:text-white pt-4">Your Tickets</h2>
            {tickets.length === 0 ? (
              <p className="text-sm text-gray-500">No support tickets yet.</p>
            ) : (
              <div className="space-y-2">
                {tickets.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => router.push(`/support/${t.id}`)}
                    className="w-full text-left p-4 rounded-xl border border-gray-200 dark:border-white/10 hover:border-orange-500/30 transition-colors flex items-center justify-between"
                  >
                    <div>
                      <p className="font-semibold text-sm text-gray-900 dark:text-white">{t.subject}</p>
                      <p className="text-xs text-gray-500">{t.ticket_number} • {new Date(t.created_at).toLocaleDateString()}</p>
                    </div>
                    <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-orange-500/10 text-orange-600 capitalize">
                      {t.status.replace("_", " ")}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <Card className="border-0 shadow-large h-fit">
            <CardContent className="p-6">
              <div className="flex items-center gap-2 mb-6">
                <MessageCircle className="w-5 h-5 text-orange-500" />
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">Contact Support</h2>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">Category</label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value as TicketCategory)}
                    className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4 text-sm"
                  >
                    {CATEGORY_OPTIONS.map((opt) => (
                      <option key={opt.id} value={opt.id}>{opt.label}</option>
                    ))}
                  </select>
                </div>

                <Input
                  placeholder="Subject"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4"
                  required
                />

                <textarea
                  placeholder="Describe your issue..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={5}
                  className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4 text-sm resize-none"
                  required
                />

                {error && (
                  <div className="flex items-center gap-2 text-sm text-red-600">
                    <AlertCircle className="w-4 h-4" /> {error}
                  </div>
                )}
                {success && (
                  <div className="text-sm text-emerald-600 font-medium">{success}</div>
                )}

                <Button
                  type="submit"
                  disabled={isSubmitting || !subject || !description}
                  className="w-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 disabled:opacity-60"
                >
                  {isSubmitting ? "Submitting..." : "Submit Ticket"}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
