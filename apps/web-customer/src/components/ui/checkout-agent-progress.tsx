"use client"

import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { Bot, AlertTriangle, CheckCircle2 } from "lucide-react"
import { AGENT_STEP_LABELS, AGENT_STEP_ORDER, watchAgentStatus } from "@/lib/agent-api"

interface CheckoutAgentProgressProps {
  orderId: number
  onDone?: (result: { status: string }) => void
}

const FAILED_STATUSES = new Set(["failed", "hitl_escalated", "cancelled"])

/**
 * Real, live checkout-agent progress driven by the SSE stream at
 * /api/agent-status/[orderId] — replaces the previous agentic-engine.tsx
 * mock, which simulated steps with Math.random() timers and was never
 * actually wired into any route.
 */
export function CheckoutAgentProgress({ orderId, onDone }: CheckoutAgentProgressProps) {
  const [step, setStep] = useState<string>("queued")
  const [status, setStatus] = useState<string>("queued")
  const [unavailable, setUnavailable] = useState(false)
  const doneRef = useRef(false)

  useEffect(() => {
    doneRef.current = false
    const unsubscribe = watchAgentStatus(
      orderId,
      (event) => {
        if (event.error) {
          setUnavailable(true)
          return
        }
        if (event.step) setStep(event.step)
        if (event.status) setStatus(event.status)
        if (event.done && !doneRef.current) {
          doneRef.current = true
          onDone?.({ status: event.status ?? "succeeded" })
        }
      },
      () => setUnavailable(true)
    )
    return unsubscribe
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId])

  if (unavailable) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-[var(--section-border)] bg-[var(--section-bg)] px-4 py-3 text-sm text-theme-muted">
        <Bot className="h-4 w-4" />
        Purchase agent status isn&apos;t available yet — we&apos;ll notify you once it starts.
      </div>
    )
  }

  const failed = FAILED_STATUSES.has(status)
  const succeeded = status === "succeeded"
  const currentIndex = Math.max(AGENT_STEP_ORDER.indexOf(step), 0)

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Bot className={`h-4 w-4 ${failed ? "text-[var(--danger)]" : "text-[var(--accent)]"}`} />
        <span className="text-sm font-semibold text-theme">
          {failed ? "Purchase needs manual review" : succeeded ? "Purchase complete" : "Purchase agent working"}
        </span>
      </div>

      {failed ? (
        <div className="flex items-center gap-2 rounded-xl border border-[var(--danger)]/20 bg-[var(--danger-bg)] px-4 py-2.5 text-sm text-[var(--danger)]">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Our operations team has been notified and will complete this purchase manually.
        </div>
      ) : (
        <div className="space-y-2">
          {AGENT_STEP_ORDER.map((code, index) => {
            const isDone = succeeded || index < currentIndex
            const isActive = !succeeded && index === currentIndex
            return (
              <div key={code} className="flex items-center gap-2.5">
                <div
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 text-[9px] font-bold ${
                    isDone
                      ? "border-[var(--success)] bg-[var(--success)] text-white"
                      : isActive
                      ? "border-[var(--accent)] text-[var(--accent)]"
                      : "border-[var(--section-border)] text-theme-muted"
                  }`}
                >
                  {isDone ? <CheckCircle2 className="h-3 w-3" /> : index + 1}
                </div>
                <span
                  className={`text-xs ${
                    isDone || isActive ? "font-medium text-theme" : "text-theme-muted"
                  }`}
                >
                  {AGENT_STEP_LABELS[code] ?? code}
                </span>
                {isActive && (
                  <motion.span
                    className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]"
                    animate={{ opacity: [1, 0.3, 1] }}
                    transition={{ duration: 1.2, repeat: Infinity }}
                  />
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
