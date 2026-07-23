"use client"

import { motion } from "framer-motion"
import { useState } from "react"
import { Eye, EyeOff, Lock, Shield, Phone, CheckCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { authApi, toE164Pakistan } from "@/lib/auth-api"
import { ApiError } from "@/lib/api-client"

const LOGIN_ERROR_MESSAGES: Record<string, string> = {
  "Invalid credentials": "Incorrect mobile number or password.",
  "Account is temporarily locked": "Too many failed attempts. Your account is temporarily locked.",
}

export default function Login() {
  const [formData, setFormData] = useState({
    mobileNumber: "",
    password: ""
  })
  const [errors, setErrors] = useState({
    mobileNumber: "",
    password: ""
  })
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const router = useRouter()

  const validateField = (name: string, value: string) => {
    let errorMsg = ""
    if (name === "mobileNumber") {
      const cleanVal = value.trim()
      if (!cleanVal) {
        errorMsg = "Mobile number is required"
      } else {
        const pkPhoneRegex = /^(?:\+92|92|0)?3\d{9}$/
        if (!pkPhoneRegex.test(cleanVal)) {
          errorMsg = "Enter a valid Pakistani mobile number (e.g. 03001234567)"
        }
      }
    } else if (name === "password") {
      if (!value) {
        errorMsg = "Password is required"
      } else if (value.length < 6) {
        errorMsg = "Password must be at least 6 characters"
      }
    }
    return errorMsg
  }

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    setErrors(prev => ({ ...prev, [field]: validateField(field, value) }))
    setError("")
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    const mobileError = validateField("mobileNumber", formData.mobileNumber)
    const passwordError = validateField("password", formData.password)

    if (mobileError || passwordError) {
      setErrors({
        mobileNumber: mobileError,
        password: passwordError
      })
      setError("Please fix the validation errors below")
      return
    }

    setIsSubmitting(true)
    try {
      await authApi.login(toE164Pakistan(formData.mobileNumber), formData.password)
      router.push('/dashboard')
    } catch (err) {
      const message = err instanceof ApiError
        ? LOGIN_ERROR_MESSAGES[String(err.detail)] ?? String(err.detail)
        : "Something went wrong. Please try again."
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div
      className="min-h-screen lg:h-screen flex relative overflow-y-auto lg:overflow-hidden"
      style={{
        backgroundImage:
          "linear-gradient(180deg, rgba(15,23,42,0.18), rgba(15,23,42,0.3)), url('https://images.unsplash.com/photo-1515165562835-c6f0d3a79659?auto=format&fit=crop&w=1600&q=80')",
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
    >
      <div className="absolute inset-0 bg-black/25 dark:bg-black/65" />

      {/* Left Panel - Login Form */}
      <motion.div
        initial={{ x: -100, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="relative z-10 w-full lg:w-1/2 h-full bg-[#FFF7ED] dark:bg-[#161413] border-r border-[var(--section-border)] px-6 py-10 sm:px-10 lg:px-14 flex flex-col justify-start items-center transition-colors duration-300 pt-32 lg:pt-28 overflow-y-auto"
      >
        <div className="w-full max-w-md space-y-6 text-left">
          <motion.div
            initial={{ y: -20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.2, duration: 0.6 }}
            className="space-y-2"
          >
            <span className="inline-flex items-center gap-1.5 rounded-full bg-orange-500/10 border border-orange-500/20 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-orange-650 dark:text-orange-400">
              🔑 SECURE ENTRY POINT
            </span>
            <h1 className="text-3xl lg:text-4xl font-black text-gray-900 dark:text-white tracking-tight">
              Welcome <span className="text-orange-500">Back</span>
            </h1>
            <p className="text-gray-600 dark:text-gray-400 text-sm">
              Sign in to manage your Shariah financing.
            </p>
          </motion.div>

          <motion.form
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.4, duration: 0.6 }}
            onSubmit={handleLogin}
            className="space-y-5"
          >
            <div className="space-y-1.5">
              <label className="block text-[10px] font-extrabold tracking-widest text-gray-400 uppercase font-mono">
                MOBILE NUMBER
              </label>
              <div className="relative">
                <Phone className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  type="text"
                  placeholder="Enter mobile number"
                  value={formData.mobileNumber}
                  onChange={(e) => handleInputChange('mobileNumber', e.target.value)}
                  className={`w-full pl-10 pr-4 py-3 rounded-xl border transition-all duration-305 focus:ring-2 bg-white dark:bg-white/5 ${
                    errors.mobileNumber
                      ? "border-rose-500 focus:ring-rose-500/50 dark:border-rose-500/50 text-rose-600 dark:text-rose-400"
                      : "border-gray-300 dark:border-white/10 focus:ring-orange-500"
                  }`}
                />
              </div>
              {errors.mobileNumber && (
                <motion.p
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-xs text-rose-500 dark:text-rose-450 font-medium pl-1"
                >
                  {errors.mobileNumber}
                </motion.p>
              )}
            </div>

            <div className="space-y-1.5">
              <label className="block text-[10px] font-extrabold tracking-widest text-gray-400 uppercase font-mono">
                PASSWORD
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter account password"
                  value={formData.password}
                  onChange={(e) => handleInputChange('password', e.target.value)}
                  className={`w-full pl-10 pr-12 py-3 rounded-xl border transition-all duration-305 focus:ring-2 bg-white dark:bg-white/5 ${
                    errors.password
                      ? "border-rose-500 focus:ring-rose-500/50 dark:border-rose-500/50 text-rose-600 dark:text-rose-400"
                      : "border-gray-300 dark:border-white/10 focus:ring-orange-500"
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-350 cursor-pointer"
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
              {errors.password && (
                <motion.p
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-xs text-rose-500 dark:text-rose-455 font-medium pl-1"
                >
                  {errors.password}
                </motion.p>
              )}
            </div>

            {error && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-rose-500/10 border border-rose-500/20 text-rose-500 px-4 py-3 rounded-xl text-xs font-mono"
              >
                {error}
              </motion.div>
            )}

            <Button
              type="submit"
              disabled={isSubmitting}
              className="w-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 shadow-lg hover:shadow-xl transition-all duration-300 py-6 rounded-xl font-bold text-white btn-smooth cursor-pointer disabled:opacity-60"
            >
              {isSubmitting ? "Signing In..." : "Sign In to Account"}
            </Button>

            <div className="flex justify-between items-center text-xs">
              <Link
                href="/auth/forgot-password"
                className="text-orange-500 hover:text-orange-600 transition"
              >
                Forgot your password?
              </Link>
              <p className="text-gray-600 dark:text-gray-400">
                New user?{" "}
                <Link
                  href="/auth/register"
                  className="text-orange-500 font-bold hover:text-orange-600 transition-colors"
                >
                  Sign up
                </Link>
              </p>
            </div>
          </motion.form>

          <motion.div
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.6, duration: 0.6 }}
            className="flex items-center justify-center space-x-8 text-[10px] text-gray-500 font-mono tracking-wider pt-6 border-t border-gray-200 dark:border-white/5"
          >
            <div className="flex items-center space-x-2">
              <Shield className="w-4 h-4 text-orange-500" />
              <span>FOLLOWS SECP CODE</span>
            </div>
            <div className="flex items-center space-x-2">
              <CheckCircle className="w-4 h-4 text-orange-500" />
              <span>Shariah Certified</span>
            </div>
          </motion.div>
        </div>
      </motion.div>

      {/* Right Panel - Trust & Security Centerpiece */}
      <motion.div
        initial={{ x: 100, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
        className="hidden lg:flex w-1/2 h-full bg-gradient-to-br from-slate-900 via-slate-950 to-orange-950/20 p-16 flex-col justify-start items-center relative border-l border-white/5 pt-32 lg:pt-28 overflow-y-auto"
      >
        {/* Ambient mesh background effects */}
        <div className="absolute top-1/4 right-1/4 w-80 h-80 rounded-full bg-orange-500/10 blur-3xl pointer-events-none" />

        <div className="text-center text-white max-w-lg relative space-y-8">

          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.4, duration: 0.6 }}
            className="space-y-6"
          >
            {/* Centerpiece Image of credit card/key portal */}
            <motion.div
              animate={{ y: [0, -10, 0] }}
              transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
              className="w-full max-w-[280px] aspect-[4/5] rounded-[2rem] border border-white/10 overflow-hidden shadow-2xl relative group mx-auto bg-slate-900"
            >
              <img
                src="/images/login_premium_render.png"
                alt="SahulatKar Premium Security Centerpiece"
                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 opacity-90"
              />
              <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-white/5 to-transparent shimmer pointer-events-none" />
            </motion.div>

            {/* Certified Badge */}
            <div className="flex justify-center">
              <span className="inline-flex items-center gap-1.5 bg-orange-500/15 border border-orange-500/20 text-orange-400 px-4 py-2 rounded-full font-bold text-xs uppercase tracking-widest font-mono">
                <CheckCircle className="w-4 h-4 text-orange-500 animate-pulse" />
                SHARIAH CERTIFIED PLATFORM
              </span>
            </div>

            <h2 className="text-3xl font-black mb-4 tracking-tight">
              Invest with Confidence
            </h2>

            <p className="text-gray-300 text-base leading-relaxed max-w-sm mx-auto">
              Join 50,000+ Pakistanis building ethical wealth through our Shariah-compliant digital custodian platform.
            </p>
          </motion.div>

          <motion.div
            initial={{ y: 50, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.6, duration: 0.6 }}
            className="space-y-2 pt-6 border-t border-white/5"
          >
            {/* User avatars */}
            <div className="flex justify-center -space-x-3 mb-2">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="w-9 h-9 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 border-2 border-slate-950 flex items-center justify-center text-white font-bold text-xs shadow-md"
                >
                  {i}
                </div>
              ))}
            </div>

            <p className="text-[10px] font-mono tracking-widest text-slate-400 uppercase">
              HIGHLY TRUSTED FINTECH PORTAL
            </p>
          </motion.div>
        </div>
      </motion.div>
    </div>
  )
}
