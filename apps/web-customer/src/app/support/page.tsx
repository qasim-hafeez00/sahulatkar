"use client"

import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { LifeBuoy, Mail, MessageCircle, Phone, ChevronDown, AlertCircle, CalendarClock, RotateCcw, Ticket } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { ApiError } from "@/lib/api-client"
import { supportApi, type TicketCategory, type TicketSummary } from "@/lib/support-api"
import { getTicketStatusMeta, TONE_STYLES } from "@/lib/status"

const CATEGORY_OPTIONS: { id: TicketCategory; label: string }[] = [
  { id: "general", label: "General Question" },
  { id: "account_issue", label: "Account Issue" },
  { id: "kyc_query", label: "KYC / Verification" },
  { id: "contract_query", label: "Financing Contract" },
  { id: "product_issue", label: "Product Issue" },
]

const FAQS = [
  { q: "How does Shariah-compliant financing work?", a: "SahulatKar uses a Murabaha (cost-plus-profit sale) structure preceded by a Wakalah (agency) agreement so we can purchase the product on your behalf, then sell it to you at a fixed, disclosed profit — no interest is ever charged." },
  { q: "How do I check my payment schedule?", a: "Visit Repayments from the navigation menu to see every upcoming and past installment across your active financing." },
  { q: "What happens if I miss an installment?", a: "Contact support as soon as possible. A late fee may apply per your signed Murabaha contract — 100% of it goes to charity, never to SahulatKar — and repeated missed payments can affect your credit limit." },
  { q: "Can I return a product I financed?", a: "Use Dispute & Refunds below to submit a request for an eligible order. Our team reviews it and responds through your ticket." },
]

const QUICK_ACTIONS = [
  { label: "Track an Order", description: "See delivery status and courier updates", icon: CalendarClock, href: "/payments/order-tracking" },
  { label: "Repayments", description: "View or pay an upcoming installment", icon: Ticket, href: "/repayment" },
  { label: "Dispute & Refunds", description: "Report a damaged, wrong, or undelivered item", icon: RotateCcw, href: "/support/dispute" },
]

function SupportSkeleton() {
  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto max-w-5xl px-4 animate-pulse">
        <div className="card-surface h-10 w-60 rounded-xl mb-3" />
        <div className="card-surface h-5 w-80 rounded-lg mb-8" />
        <div className="grid lg:grid-cols-2 gap-8">
          <div className="card-surface h-96 rounded-2xl" />
          <div className="card-surface h-96 rounded-2xl" />
        </div>
      </div>
    </div>
  )
}

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

  const loadTickets = () => {
    supportApi.list().then(setTickets).finally(() => setLoaded(true))
  }

  useEffect(() => {
    // Auth is enforced server-side by middleware.ts before this page ever renders.
    loadTickets()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setSuccess("")
    setIsSubmitting(true)
    try {
      const ticket = await supportApi.create({ category, subject, description })
      setSuccess(`Ticket ${ticket.ticket_number} created — our team will respond here.`)
      setSubject("")
      setDescription("")
      loadTickets()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not submit your request. Please try again.")
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!loaded) return <SupportSkeleton />

  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto max-w-5xl px-4">
        <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.6 }} className="mb-8">
          <h1 className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight mb-1.5">Help &amp; Support</h1>
          <p className="text-gray-600 dark:text-gray-400">Find an answer below, or reach our team directly</p>
          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-gray-500 dark:text-gray-400">
            <span className="flex items-center gap-2"><Phone className="w-4 h-4 text-orange-500" /> 0800-SAHULAT</span>
            <span className="flex items-center gap-2"><Mail className="w-4 h-4 text-orange-500" /> support@sahulatkar.pk</span>
          </div>
        </motion.div>

        {/* Quick actions */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="grid sm:grid-cols-3 gap-4 mb-8"
        >
          {QUICK_ACTIONS.map((action) => {
            const ActionIcon = action.icon
            return (
              <button
                key={action.label}
                onClick={() => router.push(action.href)}
                className="card-surface p-5 text-left hover:-translate-y-1 transition-transform duration-300"
              >
                <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center mb-3">
                  <ActionIcon className="w-5 h-5 text-orange-500" />
                </div>
                <h3 className="font-bold text-sm text-gray-900 dark:text-white mb-1">{action.label}</h3>
                <p className="text-xs text-gray-500">{action.description}</p>
              </button>
            )
          })}
        </motion.div>

        <div className="grid lg:grid-cols-2 gap-8">
          <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, delay: 0.2 }} className="space-y-4">
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">Frequently Asked Questions</h2>
            {FAQS.map((faq, i) => (
              <Card key={i} className="card-surface">
                <CardContent className="p-0">
                  <button
                    className="w-full flex items-center justify-between p-4 text-left"
                    onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  >
                    <span className="font-semibold text-gray-900 dark:text-white text-sm pr-4">{faq.q}</span>
                    <ChevronDown className={`w-4 h-4 text-gray-400 flex-none transition-transform ${openFaq === i ? "rotate-180" : ""}`} />
                  </button>
                  {openFaq === i && (
                    <p className="px-4 pb-4 text-sm text-gray-600 dark:text-gray-400 leading-relaxed">{faq.a}</p>
                  )}
                </CardContent>
              </Card>
            ))}

            <h2 className="text-lg font-bold text-gray-900 dark:text-white pt-4">Your Tickets</h2>
            {tickets.length === 0 ? (
              <p className="text-sm text-gray-500">No support tickets yet — submit one and it&apos;ll show up here.</p>
            ) : (
              <div className="space-y-2">
                {tickets.map((t) => {
                  const meta = getTicketStatusMeta(t.status)
                  const tone = TONE_STYLES[meta.tone]
                  const ToneIcon = tone.icon
                  return (
                    <button
                      key={t.id}
                      onClick={() => router.push(`/support/${t.id}`)}
                      className="w-full text-left card-surface p-4 flex items-center justify-between gap-4"
                    >
                      <div className="min-w-0">
                        <p className="font-semibold text-sm text-gray-900 dark:text-white truncate">{t.subject}</p>
                        <p className="text-xs text-gray-500">{t.ticket_number} • {new Date(t.created_at).toLocaleDateString()}</p>
                      </div>
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border flex-none ${tone.badge}`}>
                        <ToneIcon className="w-3.5 h-3.5" />
                        {meta.label}
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </motion.div>

          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, delay: 0.2 }}>
            <Card className="card-surface h-fit">
              <CardContent className="p-6">
                <div className="flex items-center gap-2 mb-6">
                  <MessageCircle className="w-5 h-5 text-orange-500" />
                  <h2 className="text-lg font-bold text-gray-900 dark:text-white">Contact Support</h2>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                  <div>
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">Category</label>
                    <select
                      value={category}
                      onChange={(e) => setCategory(e.target.value as TicketCategory)}
                      className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 text-gray-900 dark:text-white py-3 px-4 text-sm"
                    >
                      {CATEGORY_OPTIONS.map((opt) => (
                        <option key={opt.id} value={opt.id}>{opt.label}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">Subject</label>
                    <Input
                      placeholder="A short summary of your issue"
                      value={subject}
                      onChange={(e) => setSubject(e.target.value)}
                      className="w-full h-12 rounded-xl"
                      required
                    />
                  </div>

                  <div>
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">Description</label>
                    <textarea
                      placeholder="What happened, and what order or payment it relates to"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={5}
                      className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 text-gray-900 dark:text-white py-3 px-4 text-sm resize-none"
                      required
                    />
                  </div>

                  {error && (
                    <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                      <AlertCircle className="w-4 h-4 flex-none" /> {error}
                    </div>
                  )}
                  {success && (
                    <div className="text-sm text-emerald-600 dark:text-emerald-400 font-medium">{success}</div>
                  )}

                  <Button
                    type="submit"
                    disabled={isSubmitting || !subject || !description}
                    className="w-full h-14 rounded-xl font-bold bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 shadow-lg shadow-orange-500/10 btn-smooth disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    <LifeBuoy className="w-5 h-5" />
                    {isSubmitting ? "Submitting…" : "Submit Ticket"}
                  </Button>
                </form>
              </CardContent>
            </Card>
          </motion.div>
        </div>
      </div>
    </div>
  )
}
