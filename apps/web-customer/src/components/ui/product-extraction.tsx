"use client"

import { motion, AnimatePresence } from "framer-motion"
import { useEffect, useState } from "react"
import { Link2, Sparkles, ArrowRight, ShieldCheck } from "lucide-react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { ProgressTimeline, type TimelineStep } from "@/components/ui/progress-timeline"
import { SkeletonProductCard } from "@/components/ui/skeleton"
import { MonthlyMoney } from "@/components/ui/money"

const DEMO_STEPS: TimelineStep[] = [
  { key: "paste", label: "Link pasted" },
  { key: "analyze", label: "AI analyzing" },
  { key: "priced", label: "Priced & financed" },
]

const DEMO_URL = "daraz.pk/products/iphone-15-pro-max-256gb"
const DEMO_PRODUCT = {
  name: "iPhone 15 Pro Max 256GB",
  store: "Daraz.pk",
  price: 319999,
  downPaymentPct: 25,
  monthly: 19999,
}

// Cycle: 0 = link just "pasted" (typing), 1 = analyzing, 2 = priced & financed, held, then repeats.
const STEP_DURATIONS_MS = [1400, 1600, 3400]

export function ProductExtraction() {
  const router = useRouter()
  const [step, setStep] = useState(0)

  useEffect(() => {
    const timer = setTimeout(() => {
      setStep((prev) => (prev + 1) % STEP_DURATIONS_MS.length)
    }, STEP_DURATIONS_MS[step])
    return () => clearTimeout(timer)
  }, [step])

  return (
    <div className="theme-section relative overflow-hidden py-28 md:py-32">
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-10 left-1/2 h-96 w-[42rem] -translate-x-1/2 rounded-full bg-gradient-to-br from-orange-300/30 to-pink-300/10 blur-3xl opacity-70" />
      </div>
      <div className="container relative z-10 mx-auto px-4">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="mb-16 text-center"
        >
          <h2 className="mb-4 text-4xl font-bold text-theme lg:text-5xl">
            Paste a link.{" "}
            <span className="bg-gradient-to-r from-orange-500 to-pink-500 bg-clip-text text-transparent">
              We do the rest.
            </span>
          </h2>
          <p className="mx-auto max-w-2xl text-xl text-theme-muted">
            Here&apos;s what happens the moment you drop a product URL in after signing up
          </p>
        </motion.div>

        <div className="mx-auto max-w-2xl">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="theme-panel overflow-hidden rounded-3xl shadow-2xl"
          >
            {/* Mock URL bar */}
            <div className="border-b border-[var(--section-border)] p-5">
              <div className="flex items-center gap-3 rounded-xl bg-[var(--section-bg)] px-4 py-3">
                <Link2 className="h-4 w-4 shrink-0 text-theme-muted" />
                <div className="flex-1 overflow-hidden font-mono text-sm text-theme-muted">
                  <AnimatePresence mode="wait">
                    {step === 0 ? (
                      <motion.span
                        key="typing"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                      >
                        <TypingText text={DEMO_URL} />
                      </motion.span>
                    ) : (
                      <motion.span
                        key="typed"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                      >
                        {DEMO_URL}
                      </motion.span>
                    )}
                  </AnimatePresence>
                </div>
                {step >= 1 && (
                  <motion.div initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}>
                    <Sparkles className="h-4 w-4 text-[var(--accent)]" />
                  </motion.div>
                )}
              </div>
            </div>

            {/* Progress timeline */}
            <div className="border-b border-[var(--section-border)] px-6 py-5">
              <ProgressTimeline steps={DEMO_STEPS} activeIndex={step === 2 ? 3 : step} />
            </div>

            {/* Result area */}
            <div className="p-6">
              <AnimatePresence mode="wait">
                {step < 2 ? (
                  <motion.div
                    key="loading"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    <SkeletonProductCard />
                  </motion.div>
                ) : (
                  <motion.div
                    key="result"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.35 }}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <h3 className="font-semibold text-theme">{DEMO_PRODUCT.name}</h3>
                        <p className="text-sm text-theme-muted">
                          {DEMO_PRODUCT.store} &middot; {DEMO_PRODUCT.downPaymentPct}% down payment
                        </p>
                      </div>
                      <span className="shrink-0 rounded-full bg-[var(--success-bg)] px-3 py-1 text-xs font-semibold text-[var(--success)]">
                        Approved
                      </span>
                    </div>
                    <div className="mt-4 flex items-end justify-between border-t border-[var(--section-border)] pt-4">
                      <MonthlyMoney monthly={DEMO_PRODUCT.monthly} total={DEMO_PRODUCT.price} />
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* CTA */}
            <div className="flex flex-col items-center gap-3 border-t border-[var(--section-border)] bg-[var(--section-bg)] px-6 py-6 sm:flex-row sm:justify-between">
              <div className="flex items-center gap-2 text-xs text-theme-muted">
                <ShieldCheck className="h-4 w-4 text-[var(--success)]" />
                Illustrative preview &mdash; create a free account to try it on a real link
              </div>
              <Button onClick={() => router.push("/auth/register")} className="w-full sm:w-auto">
                Get started free
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  )
}

function TypingText({ text }: { text: string }) {
  const [visibleChars, setVisibleChars] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setVisibleChars((prev) => {
        if (prev >= text.length) {
          clearInterval(interval)
          return prev
        }
        return prev + 1
      })
    }, 35)
    return () => clearInterval(interval)
  }, [text])

  return (
    <>
      {text.slice(0, visibleChars)}
      <span className="animate-pulse">|</span>
    </>
  )
}
