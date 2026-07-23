"use client"

import { motion } from "framer-motion"
import { useState } from "react"
import { ArrowRight, Shield, CheckCircle, User, Phone, Mail, Tag, Cpu, ShieldAlert, Award, Lock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { authApi, toE164Pakistan } from "@/lib/auth-api"
import { ApiError } from "@/lib/api-client"

const REGISTER_ERROR_MESSAGES: Record<string, string> = {
  PHONE_ALREADY_REGISTERED: "This mobile number is already registered. Try signing in instead.",
}

export default function Register() {
  const [formData, setFormData] = useState({
    fullName: "",
    mobileNumber: "",
    emailAddress: "",
    referral: "",
    password: ""
  })
  const [errors, setErrors] = useState({
    fullName: "",
    mobileNumber: "",
    emailAddress: "",
    referral: "",
    password: ""
  })
  const [error, setError] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const router = useRouter()

  const validateField = (name: string, value: string) => {
    let errorMsg = ""
    const cleanVal = value.trim()
    if (name === "fullName") {
      if (!cleanVal) {
        errorMsg = "Full legal name is required"
      } else if (cleanVal.length < 3) {
        errorMsg = "Name must be at least 3 characters"
      } else if (!/^[a-zA-Z\s]+$/.test(cleanVal)) {
        errorMsg = "Name must only contain alphabets and spaces"
      }
    } else if (name === "mobileNumber") {
      if (!cleanVal) {
        errorMsg = "Mobile number is required"
      } else {
        const pkPhoneRegex = /^(?:\+92|92|0)?3\d{9}$/
        if (!pkPhoneRegex.test(cleanVal)) {
          errorMsg = "Enter a valid Pakistani mobile number (e.g. 03001234567)"
        }
      }
    } else if (name === "emailAddress") {
      if (!cleanVal) {
        errorMsg = "Email address is required"
      } else {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
        if (!emailRegex.test(cleanVal)) {
          errorMsg = "Enter a valid email address (e.g. name@example.com)"
        }
      }
    } else if (name === "referral") {
      if (cleanVal && !/^[a-zA-Z0-9]{4,12}$/.test(cleanVal)) {
        errorMsg = "Referral code must be alphanumeric (4-12 characters)"
      }
    } else if (name === "password") {
      if (!value) {
        errorMsg = "Password is required"
      } else if (value.length < 8) {
        errorMsg = "Password must be at least 8 characters"
      }
    }
    return errorMsg
  }

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    setErrors(prev => ({ ...prev, [field]: validateField(field, value) }))
    setError("")
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    const fullNameError = validateField("fullName", formData.fullName)
    const mobileError = validateField("mobileNumber", formData.mobileNumber)
    const emailError = validateField("emailAddress", formData.emailAddress)
    const referralError = validateField("referral", formData.referral)
    const passwordError = validateField("password", formData.password)

    if (fullNameError || mobileError || emailError || referralError || passwordError) {
      setErrors({
        fullName: fullNameError,
        mobileNumber: mobileError,
        emailAddress: emailError,
        referral: referralError,
        password: passwordError
      })
      setError("Please fix the validation errors below before creating your account")
      return
    }

    const [firstName, ...rest] = formData.fullName.trim().split(/\s+/)
    const lastName = rest.length > 0 ? rest.join(" ") : firstName

    setIsSubmitting(true)
    try {
      const result = await authApi.registerInitiate({
        phone: toE164Pakistan(formData.mobileNumber),
        first_name: firstName,
        last_name: lastName,
        email: formData.emailAddress || undefined,
        referral_code: formData.referral || undefined,
        password: formData.password,
      })
      sessionStorage.setItem("sk_otp_token", result.otp_token)
      sessionStorage.setItem("sk_otp_phone", result.masked_phone)
      sessionStorage.setItem("sk_otp_next", "/auth/cnic-front")
      if (result.dev_otp) {
        sessionStorage.setItem("sk_otp_dev_code", result.dev_otp)
      }
      router.push('/auth/otp')
    } catch (err) {
      const message = err instanceof ApiError
        ? REGISTER_ERROR_MESSAGES[String(err.detail)] ?? String(err.detail)
        : "Something went wrong. Please try again."
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div
      className="min-h-screen lg:h-screen flex flex-col lg:flex-row relative overflow-y-auto lg:overflow-hidden"
      style={{
        backgroundImage:
          "linear-gradient(180deg, rgba(15,23,42,0.18), rgba(15,23,42,0.3)), url('https://images.unsplash.com/photo-1515165562835-c6f0d3a79659?auto=format&fit=crop&w=1600&q=80')",
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
    >
      <div className="absolute inset-0 bg-black/25 dark:bg-black/65" />
      
      {/* Left Panel - Registration Form */}
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
              🌱 SHARIAH ACCOUNT REGISTRATION
            </span>
            <h1 className="text-3xl lg:text-4xl font-black text-gray-900 dark:text-white tracking-tight">
              Begin Your <span className="text-orange-500">Halal</span> Wealth Journey
            </h1>
            <p className="text-gray-600 dark:text-gray-400 text-xs leading-relaxed">
              Join thousands of digital investors building their future with Shariah-compliant financing.
            </p>
          </motion.div>

          <motion.form
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.4, duration: 0.6 }}
            onSubmit={handleRegister}
            className="space-y-5"
          >
            <div className="space-y-1.5">
              <label className="block text-[10px] font-extrabold tracking-widest text-gray-400 uppercase font-mono">
                FULL LEGAL NAME
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  type="text"
                  placeholder="Enter full name matching CNIC"
                  value={formData.fullName}
                  onChange={(e) => handleInputChange("fullName", e.target.value)}
                  className={`w-full pl-10 pr-4 py-3 rounded-xl border transition-all duration-305 focus:ring-2 bg-white dark:bg-white/5 ${
                    errors.fullName 
                      ? "border-rose-500 focus:ring-rose-500/50 dark:border-rose-500/50 text-rose-600 dark:text-rose-400" 
                      : "border-gray-300 dark:border-white/10 focus:ring-orange-500"
                  }`}
                />
              </div>
              {errors.fullName && (
                <motion.p
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-xs text-rose-500 dark:text-rose-450 font-medium pl-1"
                >
                  {errors.fullName}
                </motion.p>
              )}
            </div>
            
            <div className="space-y-1.5">
              <label className="block text-[10px] font-extrabold tracking-widest text-gray-400 uppercase font-mono">
                MOBILE NUMBER
              </label>
              <div className="relative">
                <Phone className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  type="tel"
                  placeholder="+92 300 1234567"
                  value={formData.mobileNumber}
                  onChange={(e) => handleInputChange("mobileNumber", e.target.value)}
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
                  className="text-xs text-rose-500 dark:text-rose-455 font-medium pl-1"
                >
                  {errors.mobileNumber}
                </motion.p>
              )}
            </div>
            
            <div className="space-y-1.5">
              <label className="block text-[10px] font-extrabold tracking-widest text-gray-400 uppercase font-mono">
                EMAIL ADDRESS
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  type="email"
                  placeholder="your.email@example.com"
                  value={formData.emailAddress}
                  onChange={(e) => handleInputChange("emailAddress", e.target.value)}
                  className={`w-full pl-10 pr-4 py-3 rounded-xl border transition-all duration-305 focus:ring-2 bg-white dark:bg-white/5 ${
                    errors.emailAddress 
                      ? "border-rose-500 focus:ring-rose-500/50 dark:border-rose-500/50 text-rose-600 dark:text-rose-400" 
                      : "border-gray-300 dark:border-white/10 focus:ring-orange-500"
                  }`}
                />
              </div>
              {errors.emailAddress && (
                <motion.p
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-xs text-rose-500 dark:text-rose-460 font-medium pl-1"
                >
                  {errors.emailAddress}
                </motion.p>
              )}
            </div>
            
            <div className="space-y-1.5">
              <label className="block text-[10px] font-extrabold tracking-widest text-gray-400 uppercase font-mono">
                REFERRAL CODE (OPTIONAL)
              </label>
              <div className="relative">
                <Tag className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  type="text"
                  placeholder="Enter referral code"
                  value={formData.referral}
                  onChange={(e) => handleInputChange("referral", e.target.value)}
                  className={`w-full pl-10 pr-4 py-3 rounded-xl border transition-all duration-305 focus:ring-2 bg-white dark:bg-white/5 ${
                    errors.referral 
                      ? "border-rose-500 focus:ring-rose-500/50 dark:border-rose-500/50 text-rose-600 dark:text-rose-400" 
                      : "border-gray-300 dark:border-white/10 focus:ring-orange-500"
                  }`}
                />
              </div>
              {errors.referral && (
                <motion.p
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-xs text-rose-500 dark:text-rose-465 font-medium pl-1"
                >
                  {errors.referral}
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
                  type="password"
                  placeholder="At least 8 characters"
                  value={formData.password}
                  onChange={(e) => handleInputChange("password", e.target.value)}
                  className={`w-full pl-10 pr-4 py-3 rounded-xl border transition-all duration-305 focus:ring-2 bg-white dark:bg-white/5 ${
                    errors.password
                      ? "border-rose-500 focus:ring-rose-500/50 dark:border-rose-500/50 text-rose-600 dark:text-rose-400"
                      : "border-gray-300 dark:border-white/10 focus:ring-orange-500"
                  }`}
                />
              </div>
              {errors.password && (
                <motion.p
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-xs text-rose-500 dark:text-rose-465 font-medium pl-1"
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
              size="xl"
              disabled={isSubmitting}
              className="w-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 shadow-lg hover:shadow-xl transition-all duration-300 py-6 rounded-xl font-bold text-white btn-smooth cursor-pointer disabled:opacity-60"
            >
              {isSubmitting ? "Creating Account..." : "Create Secure Account"}
            </Button>

            <div className="text-center text-xs">
              <p className="text-gray-600 dark:text-gray-400">
                Already have an account?{" "}
                <Link href="/auth/login" className="text-orange-500 font-bold hover:text-orange-600 transition-colors">
                  Sign In Here
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
        className="hidden lg:flex w-1/2 h-full bg-gradient-to-br from-slate-900 via-slate-950 to-orange-950/20 p-12 flex-col justify-start items-center relative border-l border-white/5 pt-32 lg:pt-28 overflow-y-auto"
      >
        <div className="absolute top-1/4 left-1/4 w-80 h-80 rounded-full bg-orange-500/10 blur-3xl pointer-events-none" />
        
        <div className="text-center text-white max-w-lg space-y-8 relative z-10">
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.4, duration: 0.6 }}
            className="space-y-6"
          >
            <h2 className="text-2xl font-black tracking-tight">
              Trusted by 25,000+ Digital Investors
            </h2>
            
            {/* User avatars */}
            <div className="flex justify-center -space-x-3 mb-6">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div
                  key={i}
                  className="w-10 h-10 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 border-2 border-slate-950 flex items-center justify-center text-white font-bold text-[10px] shadow-lg"
                >
                  {i}
                </div>
              ))}
            </div>
            
            <p className="text-gray-300 text-sm leading-relaxed max-w-sm mx-auto">
              Your security is our priority. We use bank-level encryption and store all data on Pakistan-based servers to ensure complete compliance with local regulations.
            </p>
          </motion.div>

          <motion.div
            initial={{ y: 50, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.6, duration: 0.6 }}
            className="space-y-4 pt-6 border-t border-white/5 text-left"
          >
            <div className="bg-slate-900/60 backdrop-blur-md rounded-2xl p-5 border border-white/10 flex items-start gap-4 hover:border-orange-500/20 transition duration-300">
              <div className="w-10 h-10 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-xl flex items-center justify-center flex-shrink-0">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <div className="space-y-1">
                <h3 className="text-sm font-extrabold uppercase tracking-wide">Shariah Compliant</h3>
                <p className="text-xs text-gray-400 leading-relaxed">
                  All financial products are audited and certified by leading scholars following Islamic banking principles.
                </p>
              </div>
            </div>

            <div className="bg-slate-900/60 backdrop-blur-md rounded-2xl p-5 border border-white/10 flex items-start gap-4 hover:border-orange-500/20 transition duration-300">
              <div className="w-10 h-10 bg-gradient-to-br from-orange-500 to-orange-600 rounded-xl flex items-center justify-center flex-shrink-0">
                <Cpu className="w-5 h-5 text-white" />
              </div>
              <div className="space-y-1">
                <h3 className="text-sm font-extrabold uppercase tracking-wide">Neural Compliance</h3>
                <p className="text-xs text-gray-400 leading-relaxed">
                  Regular automated checks ensure complete compliance with SECP guidelines and local security standards.
                </p>
              </div>
            </div>
          </motion.div>
        </div>
      </motion.div>
    </div>
  )
}
