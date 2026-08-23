"use client"

import { motion } from "framer-motion"
import { Check } from "lucide-react"
import { cn } from "@/lib/utils"

export interface TimelineStep {
  key: string
  label: string
}

interface ProgressTimelineProps {
  steps: TimelineStep[]
  /** Index of the step currently in progress. Steps before it are done; steps after are upcoming. */
  activeIndex: number
  /** When true, the active step is shown as failed instead of in-progress. */
  failed?: boolean
  className?: string
}

/**
 * Compact horizontal step tracker for async flows (e.g. link pasted → AI analyzing → priced).
 * Reused wherever a multi-stage backend job needs to read as progress rather than a bare spinner.
 */
export function ProgressTimeline({ steps, activeIndex, failed = false, className }: ProgressTimelineProps) {
  return (
    <div className={cn("flex items-center", className)} role="list" aria-label="Progress">
      {steps.map((step, index) => {
        const isDone = index < activeIndex
        const isActive = index === activeIndex && activeIndex < steps.length
        const isFailed = isActive && failed
        const isUpcoming = index > activeIndex

        return (
          <div key={step.key} className="flex flex-1 items-center last:flex-none" role="listitem">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={cn(
                  "relative flex h-6 w-6 items-center justify-center rounded-full border-2 text-[10px] font-semibold transition-colors duration-300",
                  isDone && "border-[var(--success)] bg-[var(--success)] text-white",
                  isActive && !isFailed && "border-[var(--accent)] text-[var(--accent)]",
                  isFailed && "border-[var(--danger)] bg-[var(--danger)] text-white",
                  isUpcoming && "border-[var(--section-border)] text-theme-muted"
                )}
              >
                {isDone && <Check className="h-3.5 w-3.5" strokeWidth={3} />}
                {isActive && !isFailed && (
                  <motion.span
                    className="absolute inset-0 rounded-full border-2 border-[var(--accent)]"
                    animate={{ scale: [1, 1.6], opacity: [0.6, 0] }}
                    transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
                  />
                )}
                {isActive && !isFailed && <span>{index + 1}</span>}
                {isFailed && <span>!</span>}
                {isUpcoming && <span>{index + 1}</span>}
              </div>
              <span
                className={cn(
                  "whitespace-nowrap text-[11px] font-medium",
                  (isDone || isActive) && !isFailed && "text-theme",
                  isFailed && "text-[var(--danger)]",
                  isUpcoming && "text-theme-muted"
                )}
              >
                {step.label}
              </span>
            </div>
            {index < steps.length - 1 && (
              <div className="mx-2 h-0.5 flex-1 -translate-y-2.5 overflow-hidden rounded-full bg-[var(--section-border)]">
                <motion.div
                  className="h-full bg-[var(--success)]"
                  initial={false}
                  animate={{ width: index < activeIndex ? "100%" : "0%" }}
                  transition={{ duration: 0.4, ease: "easeOut" }}
                />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
