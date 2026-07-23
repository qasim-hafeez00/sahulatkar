"use client"

import { motion } from "framer-motion"
import type { ReactNode } from "react"
import { Sparkles } from "lucide-react"

type AuthPageShellProps = {
  children: ReactNode
  badge?: string
  title: string
  subtitle: string
  icon?: ReactNode
}

export function AuthPageShell({
  children,
  badge = "Secure Authentication",
  title,
  subtitle,
  icon,
}: AuthPageShellProps) {
  return (
    <div className="relative min-h-[calc(100vh-5rem)] flex items-center justify-center px-4 py-16">
      <motion.div
        initial={{ opacity: 0, y: 28, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
        className="relative w-full max-w-lg"
      >
        <div className="absolute -inset-1 rounded-[2rem] bg-gradient-to-r from-orange-400/30 via-pink-400/20 to-purple-400/30 blur-xl dark:from-orange-500/20 dark:via-pink-500/10 dark:to-purple-500/15" />

        <div className="relative overflow-hidden rounded-[2rem] border border-[var(--section-border)] bg-[var(--card-bg)] p-8 shadow-[var(--shadow-soft)] backdrop-blur-2xl dark:shadow-[var(--shadow-hover)] sm:p-10">
          <div className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full bg-orange-400/10 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-12 -left-12 h-32 w-32 rounded-full bg-pink-400/10 blur-3xl" />

          <div className="relative text-center mb-8">
            <motion.span
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
              className="inline-flex items-center gap-2 rounded-full border border-orange-200/80 bg-orange-50/80 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.2em] text-orange-700 dark:border-orange-500/25 dark:bg-orange-500/10 dark:text-orange-300"
            >
              <Sparkles className="h-3.5 w-3.5" />
              {badge}
            </motion.span>

            {icon && (
              <motion.div
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: 0.2, type: "spring", stiffness: 260 }}
                className="mx-auto mt-6 flex h-20 w-20 items-center justify-center rounded-[1.75rem] bg-gradient-to-br from-orange-500 to-orange-600 text-white shadow-xl shadow-orange-500/30"
              >
                {icon}
              </motion.div>
            )}

            <motion.h1
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25 }}
              className="mt-6 text-3xl font-bold tracking-tight text-theme"
            >
              {title}
            </motion.h1>
            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="mt-3 text-base leading-relaxed text-theme-muted"
            >
              {subtitle}
            </motion.p>
          </div>

          {children}
        </div>
      </motion.div>
    </div>
  )
}
