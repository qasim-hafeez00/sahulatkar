"use client"

import { motion } from "framer-motion"
import { useState, useEffect } from "react"
import { ArrowRight, Lock, Clock, RefreshCw, MessageCircle, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { authApi } from "@/lib/auth-api"
import { ApiError } from "@/lib/api-client"

const OTP_ERROR_MESSAGES: Record<string, string> = {
  OTP_EXPIRED: "This code has expired. Please request a new one.",
  INVALID_OTP: "Invalid OTP. Please check the code and try again.",
  TOO_MANY_ATTEMPTS: "Too many attempts. Please request a new code.",
}

export default function OTP() {
  const [otp, setOtp] = useState(["", "", "", "", "", ""])
  const [error, setError] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null)
  const [timeLeft, setTimeLeft] = useState(59)
  const [canResend, setCanResend] = useState(false)
  const [devOtp, setDevOtp] = useState<string | null>(null)
  const router = useRouter()

  useEffect(() => {
    setDevOtp(sessionStorage.getItem("sk_otp_dev_code"))
  }, [])

  useEffect(() => {
    if (timeLeft > 0) {
      const timer = setTimeout(() => setTimeLeft(timeLeft - 1), 1000)
      return () => clearTimeout(timer)
    } else {
      setCanResend(true)
    }
  }, [timeLeft])

  const handleOtpChange = (index: number, value: string) => {
    if (!/^\d*$/.test(value)) return
    if (value.length > 1) return

    const newOtp = [...otp]
    newOtp[index] = value
    setOtp(newOtp)
    setError("")

    if (value && index < 5) {
      const nextInput = document.getElementById(`otp-${index + 1}`) as HTMLInputElement
      nextInput?.focus()
    }
  }

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      const prevInput = document.getElementById(`otp-${index - 1}`) as HTMLInputElement
      prevInput?.focus()
    }
  }

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault()
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6)
    if (!pasted) return
    const newOtp = [...otp]
    pasted.split("").forEach((char, i) => {
      newOtp[i] = char
    })
    setOtp(newOtp)
  }

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    const otpToken = sessionStorage.getItem("sk_otp_token")
    if (!otpToken) {
      setError("Your session expired. Please register again.")
      return
    }

    setIsLoading(true)
    const otpValue = otp.join("")

    try {
      await authApi.verifyOtp(otpToken, otpValue)
      sessionStorage.removeItem("sk_otp_token")
      sessionStorage.removeItem("sk_otp_dev_code")
      const next = sessionStorage.getItem("sk_otp_next") ?? "/auth/cnic-front"
      sessionStorage.removeItem("sk_otp_next")
      router.push(next)
    } catch (err) {
      const message = err instanceof ApiError
        ? OTP_ERROR_MESSAGES[String(err.detail)] ?? String(err.detail)
        : "Something went wrong. Please try again."
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  const handleResend = async () => {
    setOtp(["", "", "", "", "", ""])
    setError("")

    const otpToken = sessionStorage.getItem("sk_otp_token")
    if (!otpToken) {
      setError("Your session expired. Please register again.")
      return
    }

    try {
      const result = await authApi.resendOtp(otpToken)
      sessionStorage.setItem("sk_otp_token", result.otp_token)
      if (result.dev_otp) {
        sessionStorage.setItem("sk_otp_dev_code", result.dev_otp)
        setDevOtp(result.dev_otp)
      }
      setTimeLeft(59)
      setCanResend(false)
    } catch (err) {
      const message = err instanceof ApiError
        ? OTP_ERROR_MESSAGES[String(err.detail)] ?? String(err.detail)
        : "Could not resend the code. Please try again."
      setError(message)
    }
  }

  const handleAutofill = () => {
    const demoCode = (devOtp ?? "123456").split("")
    setError("")
    demoCode.forEach((char, i) => {
      setTimeout(() => {
        setOtp(prev => {
          const next = [...prev]
          next[i] = char
          return next
        })
        const nextInput = document.getElementById(`otp-${i}`) as HTMLInputElement | null
        nextInput?.focus()
        if (i === 5) {
          setTimeout(() => {
            const verifyButton = document.getElementById("verify-btn") as HTMLButtonElement | null
            verifyButton?.focus()
          }, 120)
        }
      }, i * 80)
    })
  }

  const filledCount = otp.filter(Boolean).length

  return (
    <div className="min-h-screen lg:h-screen flex flex-col lg:flex-row relative overflow-y-auto lg:overflow-hidden bg-[#FFF7ED] dark:bg-[#161413]">
      {/* Left Panel - OTP Form */}
      <motion.div
        initial={{ x: -100, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="relative z-10 w-full lg:w-1/2 h-full bg-[#FFF7ED] dark:bg-[#161413] border-r border-[var(--section-border)] p-8 lg:p-14 flex flex-col justify-start items-center transition-colors duration-300 pt-32 lg:pt-28 overflow-y-auto"
      >
        <div className="w-full max-w-md">
          {/* Header section (styled exactly like Login page header) */}
          <div className="relative text-left mb-8">
            <motion.span
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
              className="inline-flex items-center gap-2 rounded-full border border-orange-200/80 bg-orange-50/80 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.2em] text-orange-700 dark:border-orange-500/25 dark:bg-orange-500/10 dark:text-orange-300"
            >
              🔐 TWO-FACTOR SECURITY
            </motion.span>

            <motion.h1
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25 }}
              className="mt-6 text-3xl lg:text-4xl font-bold tracking-tight text-gray-900 dark:text-white"
            >
              Verify <span className="text-orange-600">OTP</span>
            </motion.h1>
            
            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="mt-3 text-base leading-relaxed text-gray-600 dark:text-[var(--muted)]"
            >
              Enter the 6-digit code sent to your registered mobile number.
            </motion.p>
          </div>

          <form onSubmit={handleVerify}>
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.35 }}
              className="mb-6"
            >
              <div className="mb-4 flex items-center justify-between">
                <label className="text-sm font-semibold text-gray-700 dark:text-gray-300 tracking-wide">Enter OTP Code</label>
                <span className="text-xs font-bold text-orange-500 bg-orange-500/10 px-2.5 py-0.5 rounded-full">{filledCount}/6 Digits</span>
              </div>

              <div className="flex justify-between gap-2 sm:gap-3" onPaste={handlePaste}>
                {otp.map((digit, index) => (
                  <motion.input
                    key={index}
                    id={`otp-${index}`}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => handleOtpChange(index, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(index, e)}
                    onFocus={() => setFocusedIndex(index)}
                    onBlur={() => setFocusedIndex(null)}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.4 + index * 0.05 }}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    className={`h-14 w-11 sm:h-16 sm:w-14 rounded-2xl border-2 bg-white/70 dark:bg-slate-900/60 text-center text-2xl font-black text-slate-800 dark:text-white outline-none transition-all duration-300 relative ${
                      focusedIndex === index
                        ? "border-orange-500 shadow-[0_0_20px_rgba(249,115,22,0.3)] bg-white dark:bg-slate-900 scale-110 ring-2 ring-orange-500/20"
                        : digit
                          ? "border-orange-500 bg-orange-50/40 dark:bg-orange-500/10 text-orange-600 dark:text-orange-400 font-extrabold scale-105 shadow-inner"
                          : "border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 hover:bg-white/80 dark:hover:bg-slate-900/40"
                    }`}
                  />
                ))}
              </div>
            </motion.div>

            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-5 rounded-2xl border border-red-200/80 bg-red-50/80 px-4 py-3 text-sm text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300 font-medium"
              >
                {error}
              </motion.div>
            )}

            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
              className="space-y-6"
            >
              <Button
                id="verify-btn"
                type="submit"
                disabled={isLoading || otp.some((digit) => !digit)}
                className="w-full rounded-2xl bg-gradient-to-r from-orange-500 to-orange-600 py-6 text-base font-semibold shadow-lg shadow-orange-500/25 hover:from-orange-600 hover:to-orange-700 disabled:opacity-50 hover:shadow-orange-500/35 transition-all duration-300 transform active:scale-[0.98]"
              >
                {isLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Verifying Security Pin...
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-2">
                    Verify OTP
                    <ArrowRight className="h-5 w-5" />
                  </span>
                )}
              </Button>

              {/* Ticking Countdown Timer */}
              <div className="flex flex-col gap-4 text-center text-sm">
                {!canResend ? (
                  <div className="flex items-center justify-center gap-2 text-sm text-gray-500 dark:text-gray-400 font-medium bg-gray-100 dark:bg-slate-900/60 py-2.5 px-5 rounded-full w-fit mx-auto border border-gray-200/50 dark:border-slate-800/40 shadow-sm transition-all duration-300">
                    <Clock className="w-4 h-4 text-orange-500 animate-pulse" />
                    <span>Resend code in <strong className="text-orange-500 dark:text-orange-400 font-black font-mono text-base">{timeLeft}s</strong></span>
                  </div>
                ) : (
                  <motion.div 
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="flex flex-col sm:flex-row justify-center gap-3 w-full"
                  >
                    <button
                      type="button"
                      onClick={handleResend}
                      className="inline-flex items-center justify-center gap-2 font-bold text-orange-600 hover:text-orange-700 dark:text-orange-400 dark:hover:text-orange-300 bg-orange-500/10 hover:bg-orange-500/20 py-2.5 px-5 rounded-xl transition-all duration-300 transform hover:-translate-y-0.5 border border-orange-500/20 shadow-sm"
                    >
                      <RefreshCw className="w-4 h-4 animate-spin-slow" />
                      <span>Resend via SMS</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleResend}
                      className="inline-flex items-center justify-center gap-2 font-bold text-green-600 hover:text-green-700 dark:text-green-400 dark:hover:text-green-300 bg-green-500/10 hover:bg-green-500/20 py-2.5 px-5 rounded-xl transition-all duration-300 transform hover:-translate-y-0.5 border border-green-500/20 shadow-sm"
                    >
                      <MessageCircle className="w-4 h-4" />
                      <span>Get on WhatsApp</span>
                    </button>
                  </motion.div>
                )}

                <Link href="/auth/login" className="text-gray-500 dark:text-gray-400 transition hover:text-orange-600 dark:hover:text-orange-400 font-medium hover:underline mt-1">
                  Back to Login
                </Link>
              </div>
            </motion.div>

            {/* Dev-only autofill card — the gateway returns dev_otp outside production */}
            {devOtp && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.6 }}
                onClick={handleAutofill}
                className="group relative mt-8 cursor-pointer overflow-hidden rounded-2xl border border-orange-300/40 bg-gradient-to-r from-orange-50/60 to-amber-50/40 p-5 dark:border-orange-500/10 dark:from-orange-500/5 dark:to-amber-500/3 shadow-md hover:shadow-lg hover:border-orange-400/50 dark:hover:border-orange-500/20 transition-all duration-300"
              >
                {/* background accent blur */}
                <div className="absolute -top-8 -right-8 w-24 h-24 bg-orange-400/10 rounded-full blur-xl group-hover:scale-150 transition-all duration-500" />

                <div className="flex items-start gap-4 text-sm relative z-10">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-orange-500/10 text-orange-600 dark:bg-orange-500/20 dark:text-orange-400 group-hover:scale-110 transition-transform duration-300">
                    <Sparkles className="h-5 w-5 text-orange-500 dark:text-orange-400 animate-pulse" />
                  </div>
                  <div className="space-y-1 text-left">
                    <p className="text-orange-950 dark:text-orange-200 font-bold flex items-center gap-1.5">
                      <span>Dev Mode OTP</span>
                      <span className="inline-flex items-center rounded-full bg-orange-500/10 px-2.5 py-0.5 text-[9px] font-black uppercase tracking-wider text-orange-700 dark:text-orange-400 animate-pulse border border-orange-500/20">
                        Autofill
                      </span>
                    </p>
                    <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
                      Click anywhere on this card to automatically type the code the gateway generated for this session: <strong className="text-orange-600 dark:text-orange-400 font-mono font-bold text-sm bg-white/70 dark:bg-slate-900/60 px-1.5 py-0.5 rounded border border-orange-200/50 dark:border-orange-500/10">{devOtp}</strong>
                    </p>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-orange-200/40 dark:border-orange-500/5 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 relative z-10">
                  <span className="flex items-center gap-1.5">
                    <Lock className="h-3.5 w-3.5" />
                    End-to-end encrypted channel
                  </span>
                  <span className="text-orange-600 dark:text-orange-400 font-bold group-hover:translate-x-1.5 transition-transform duration-300 flex items-center gap-1">
                    Try it now <ArrowRight className="w-3.5 h-3.5" />
                  </span>
                </div>
              </motion.div>
            )}
          </form>
        </div>
      </motion.div>

      {/* Right Panel - Premium Centered Graphic Card matching sign-in/signup pages */}
      <motion.div
        initial={{ x: 100, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
        className="hidden lg:flex w-1/2 h-full bg-gradient-to-br from-gray-900 to-gray-800 p-12 flex-col justify-start items-center relative overflow-hidden pt-32 lg:pt-28 overflow-y-auto"
      >
        {/* Tech glowing background accent lines */}
        <div className="absolute inset-0 bg-gradient-to-tr from-blue-500/10 via-transparent to-orange-500/10 pointer-events-none" />
        
        {/* SK Logo in background (matching login page) */}
        <div className="absolute bottom-6 right-6 opacity-10 pointer-events-none select-none">
          <span className="text-[180px] font-black text-white">SK</span>
        </div>

        {/* Premium visual container card */}
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.4, duration: 0.6 }}
          className="relative max-w-sm w-full bg-white/5 backdrop-blur-xl border border-white/10 rounded-[2.5rem] p-6 shadow-2xl flex flex-col items-center text-center"
        >
          {/* Outer frame for the image to keep the boy and key fully visible and crisp */}
          <div className="w-64 h-64 rounded-[2rem] bg-white overflow-hidden shadow-inner border-4 border-white/20 flex items-center justify-center p-2 mb-6">
            <img
              src="https://cdn.pixabay.com/photo/2015/10/30/10/40/key-1013662_1280.jpg"
              alt="Security Key Holder"
              className="w-full h-full object-contain rounded-[1.5rem] select-none pointer-events-none"
            />
          </div>

          <h3 className="text-2xl font-bold text-white mb-2 tracking-wide">
            Secure Custody
          </h3>
          <p className="text-gray-300 text-sm leading-relaxed px-4">
            Your assets are locked under bank-grade security protocols and Shariah-compliant digital custody.
          </p>
        </motion.div>
      </motion.div>
    </div>
  )
}
