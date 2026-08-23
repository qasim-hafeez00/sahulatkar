"use client"

import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { ArrowLeft, Send, User as UserIcon, Headset } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ApiError } from "@/lib/api-client"
import { supportApi, type TicketDetail } from "@/lib/support-api"

export default function TicketDetailPage() {
  const router = useRouter()
  const params = useParams()
  const ticketId = Number(params.id)
  const [ticket, setTicket] = useState<TicketDetail | null>(null)
  const [reply, setReply] = useState("")
  const [error, setError] = useState("")
  const [isSending, setIsSending] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const load = () => {
    supportApi.get(ticketId).then(setTicket).finally(() => setLoaded(true))
  }

  useEffect(() => {
    // Auth is enforced server-side by middleware.ts before this page ever renders.
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId])

  const handleReply = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!reply.trim()) return
    setError("")
    setIsSending(true)
    try {
      await supportApi.addMessage(ticketId, reply)
      setReply("")
      await supportApi.get(ticketId).then(setTicket)
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Could not send your message.")
    } finally {
      setIsSending(false)
    }
  }

  if (!loaded) return null
  if (!ticket) {
    return (
      <div className="min-h-screen pt-28 pb-16 text-center">
        <p className="text-gray-500">Ticket not found.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen pt-28 pb-16">
      <div className="container mx-auto max-w-2xl px-4">
        <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.6 }} className="mb-6">
          <button onClick={() => router.back()} className="flex items-center gap-1 text-sm text-gray-500 hover:text-orange-500 mb-3">
            <ArrowLeft className="w-4 h-4" /> Back
          </button>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{ticket.subject}</h1>
              <p className="text-sm text-gray-500">{ticket.ticket_number} • {ticket.category.replace("_", " ")}</p>
            </div>
            <span className="text-xs font-semibold px-3 py-1.5 rounded-full bg-orange-500/10 text-orange-600 capitalize">
              {ticket.status.replace("_", " ")}
            </span>
          </div>
        </motion.div>

        <Card className="border-0 shadow-large mb-4">
          <CardContent className="p-6 space-y-4">
            {ticket.messages.map((m) => (
              <div key={m.id} className={`flex gap-3 ${m.sender_type === "user" ? "" : "flex-row-reverse text-right"}`}>
                <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${m.sender_type === "user" ? "bg-orange-100 text-orange-600" : "bg-slate-800 text-white"}`}>
                  {m.sender_type === "user" ? <UserIcon className="w-4 h-4" /> : <Headset className="w-4 h-4" />}
                </div>
                <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${m.sender_type === "user" ? "bg-gray-100 dark:bg-white/5" : "bg-orange-500/10"}`}>
                  <p className="text-gray-800 dark:text-gray-200">{m.message_text}</p>
                  <p className="text-xs text-gray-500 mt-1">{new Date(m.created_at).toLocaleString()}</p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {ticket.status !== "closed" && (
          <Card className="border-0 shadow-large">
            <CardContent className="p-4">
              <form onSubmit={handleReply} className="flex items-end gap-3">
                <textarea
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  placeholder="Type a reply..."
                  rows={2}
                  className="flex-1 rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4 text-sm resize-none"
                />
                <Button type="submit" disabled={isSending || !reply.trim()} className="bg-gradient-to-r from-orange-500 to-orange-600 disabled:opacity-60">
                  <Send className="w-4 h-4" />
                </Button>
              </form>
              {error && <p className="text-sm text-red-600 mt-2">{error}</p>}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
