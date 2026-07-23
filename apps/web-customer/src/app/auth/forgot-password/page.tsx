"use client"

import { motion } from "framer-motion"
import { useState } from "react"
import { ArrowRight, KeyRound, Lock, Phone, Sparkles, CheckCircle2 } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { authApi, toE164Pakistan } from "@/lib/auth-api"
import { ApiError } from "@/lib/api-client"

const ERROR_MESSAGES: Record<string, string> = {
  RESET_TOKEN_EXPIRED: "This reset session has expired. Please request a new code.",
  RESET_TOKEN_INVALID: "This reset session is invalid. Please request a new code.",
  INVALID_OTP: "Incorrect code. Please check and try again.",
  USER_NOT_FOUND: "We couldn't find an account for that number.",
}

export default function ForgotPassword() {
  const router = useRouter()
  const [step, setStep] = useState<"phone" | "reset" | "done">("phone")
  const [phone, setPhone] = useState("")
  const [maskedPhone, setMaskedPhone] = useState("")
  const [resetToken, setResetToken] = useState("")
  const [devOtp, setDevOtp] = useState<string | null>(null)
  const [otpCode, setOtpCode] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleRequestCode = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setIsSubmitting(true)
    try {
      const result = await authApi.forgotPassword(toE164Pakistan(phone))
      setMaskedPhone(result.masked_phone)
      setResetToken(result.reset_token)
      setDevOtp(result.dev_otp ?? null)
      setStep("reset")
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Something went wrong. Please try again.")
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.")
      return
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.")
      return
    }

    setIsSubmitting(true)
    try {
      await authApi.resetPassword(resetToken, otpCode, newPassword)
      setStep("done")
    } catch (err) {
      const message = err instanceof ApiError
        ? ERROR_MESSAGES[String(err.detail)] ?? String(err.detail)
        : "Something went wrong. Please try again."
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 pt-28 pb-16 bg-[#FFF7ED] dark:bg-[#161413]">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-md"
      >
        <Card className="border-0 shadow-large">
          <CardContent className="p-8">
            {step === "phone" && (
              <>
                <div className="mb-6 text-center">
                  <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-orange-500/10">
                    <KeyRound className="h-7 w-7 text-orange-500" />
                  </div>
                  <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Forgot your password?</h1>
                  <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                    Enter your registered mobile number and we&apos;ll send you a code to reset it.
                  </p>
                </div>

                <form onSubmit={handleRequestCode} className="space-y-4">
                  <div className="relative">
                    <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <Input
                      type="text"
                      placeholder="03001234567"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      className="w-full rounded-xl border border-gray-300 bg-white py-3 pl-10 pr-4 dark:border-white/10 dark:bg-white/5"
                      required
                    />
                  </div>

                  {error && (
                    <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
                      {error}
                    </div>
                  )}

                  <Button
                    type="submit"
                    disabled={isSubmitting || !phone}
                    className="w-full rounded-xl bg-gradient-to-r from-orange-500 to-orange-600 py-6 font-semibold text-white hover:from-orange-600 hover:to-orange-700 disabled:opacity-60"
                  >
                    {isSubmitting ? "Sending code..." : "Send reset code"}
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>

                  <p className="text-center text-sm text-gray-600 dark:text-gray-400">
                    <Link href="/auth/login" className="font-semibold text-orange-500 hover:text-orange-600">
                      Back to login
                    </Link>
                  </p>
                </form>
              </>
            )}

            {step === "reset" && (
              <>
                <div className="mb-6 text-center">
                  <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-orange-500/10">
                    <Lock className="h-7 w-7 text-orange-500" />
                  </div>
                  <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Enter your reset code</h1>
                  <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                    We sent a 6-digit code to {maskedPhone}.
                  </p>
                </div>

                {devOtp && (
                  <button
                    type="button"
                    onClick={() => setOtpCode(devOtp)}
                    className="mb-5 w-full rounded-2xl border border-orange-300/40 bg-orange-50/60 p-4 text-left text-sm transition hover:border-orange-400/60 dark:border-orange-500/10 dark:bg-orange-500/5"
                  >
                    <div className="flex items-center gap-2 font-bold text-orange-950 dark:text-orange-200">
                      <Sparkles className="h-4 w-4 text-orange-500" />
                      Dev Mode OTP — click to autofill
                    </div>
                    <p className="mt-1 font-mono text-lg font-bold text-orange-600 dark:text-orange-400">{devOtp}</p>
                  </button>
                )}

                <form onSubmit={handleReset} className="space-y-4">
                  <Input
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    placeholder="6-digit code"
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
                    className="w-full rounded-xl border border-gray-300 bg-white py-3 px-4 text-center tracking-[0.5em] font-mono dark:border-white/10 dark:bg-white/5"
                    required
                  />
                  <Input
                    type="password"
                    placeholder="New password (min. 8 characters)"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full rounded-xl border border-gray-300 bg-white py-3 px-4 dark:border-white/10 dark:bg-white/5"
                    required
                  />
                  <Input
                    type="password"
                    placeholder="Confirm new password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="w-full rounded-xl border border-gray-300 bg-white py-3 px-4 dark:border-white/10 dark:bg-white/5"
                    required
                  />

                  {error && (
                    <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
                      {error}
                    </div>
                  )}

                  <Button
                    type="submit"
                    disabled={isSubmitting || otpCode.length !== 6}
                    className="w-full rounded-xl bg-gradient-to-r from-orange-500 to-orange-600 py-6 font-semibold text-white hover:from-orange-600 hover:to-orange-700 disabled:opacity-60"
                  >
                    {isSubmitting ? "Resetting..." : "Reset password"}
                  </Button>
                </form>
              </>
            )}

            {step === "done" && (
              <div className="text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10">
                  <CheckCircle2 className="h-7 w-7 text-emerald-500" />
                </div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Password reset</h1>
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                  Your password has been changed. You can now sign in with your new password.
                </p>
                <Button
                  onClick={() => router.push("/auth/login")}
                  className="mt-6 w-full rounded-xl bg-gradient-to-r from-orange-500 to-orange-600 py-6 font-semibold text-white hover:from-orange-600 hover:to-orange-700"
                >
                  Go to login
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}
