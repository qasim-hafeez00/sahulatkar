"use client"

import { cn } from "@/lib/utils"

interface OtpInputProps {
  value: string
  onChange: (value: string) => void
  devOtp?: string | null
  className?: string
}

/**
 * 6-digit code entry with an optional dev-mode autofill affordance, used by every
 * OTP-gated step in the contract-signing flow (Wakalah, Murabaha).
 */
export function OtpInput({ value, onChange, devOtp, className }: OtpInputProps) {
  return (
    <div className={cn(className)}>
      <input
        type="text"
        inputMode="numeric"
        maxLength={6}
        value={value}
        onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
        placeholder="000000"
        className="w-full rounded-2xl border border-[var(--section-border)] bg-[var(--card-bg)] px-4 py-4 text-center text-2xl font-bold tracking-[0.5em] text-theme focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20"
      />
      {devOtp && (
        <button
          type="button"
          onClick={() => onChange(devOtp)}
          className="mt-3 w-full rounded-xl border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-4 py-2 text-xs font-semibold text-[var(--accent)] hover:bg-[var(--accent)]/15"
        >
          Dev Mode: tap to autofill code {devOtp}
        </button>
      )}
    </div>
  )
}
