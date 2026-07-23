"use client"

import { motion } from "framer-motion"
import { useEffect } from "react"
import { BadgeCheck, Shield, Sparkles, Star } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { VerificationPageShell } from "@/components/auth/verification-page-shell"
import { kycApi } from "@/lib/kyc-api"

export default function VerificationSuccess() {
  const router = useRouter()
  const [fullName, setFullName] = useState("Your Account")
  const [cnic, setCnic] = useState("")

  useEffect(() => {
    kycApi.getProfile()
      .then((profile) => {
        setFullName(`${profile.first_name} ${profile.last_name}`)
        setCnic(profile.cnic)
      })
      .catch(() => {})
  }, [])

  const handleContinue = () => {
    router.push("/cart")
  }

  const handleBack = () => {
    router.push("/auth/facial-recognition")
  }

  return (
    <VerificationPageShell
      activeStep="success"
      accent="orange"
      badge="Verification Complete"
      title="Identity Verified Successfully"
      subtitle="Your profile is authenticated and cleared for premium financial services"
    >
      <div className="grid gap-8 xl:grid-cols-[1.4fr_0.9fr]">
        {/* Left Success panel card */}
        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65 }}
          className="theme-panel relative overflow-hidden rounded-[2.5rem] p-10 shadow-[var(--shadow-soft)] border border-white/10"
        >
          {/* Glowing background highlights */}
          <div className="pointer-events-none absolute -right-10 -top-10 h-48 w-48 rounded-full bg-emerald-500/10 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-8 -left-8 h-40 w-40 rounded-full bg-orange-500/10 blur-3xl" />

          <div className="flex flex-col sm:flex-row items-center gap-6">
            {/* Centered concentric technical rotating rings around BadgeCheck */}
            <div className="relative flex items-center justify-center h-28 w-28 mx-auto sm:mx-0 shrink-0">
              {/* Tech spinning border dials */}
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
                className="absolute inset-0 rounded-[2rem] border-2 border-dashed border-emerald-500/30"
              />
              <motion.div
                animate={{ rotate: -360 }}
                transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
                className="absolute inset-2 rounded-[1.75rem] border border-emerald-400/20 border-t-emerald-400/60"
              />
              <motion.div
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ type: "spring", stiffness: 200, delay: 0.2 }}
                className="relative h-20 w-20 rounded-[1.5rem] bg-gradient-to-br from-emerald-500 to-teal-600 text-white shadow-xl shadow-emerald-500/30 flex items-center justify-center"
              >
                <BadgeCheck className="h-11 w-11 text-white" />
              </motion.div>
            </div>

            <div className="relative text-center sm:text-left">
              <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-emerald-250 bg-emerald-500/10 px-3.5 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-600 dark:text-emerald-400 border-emerald-400/25">
                <Sparkles className="h-3.5 w-3.5 text-emerald-500 dark:text-emerald-400 animate-pulse" />
                Platinum Verified
              </div>
              <h2 className="text-3xl font-bold tracking-tight text-theme sm:text-4xl">
                Welcome to SahulatKar
              </h2>
            </div>
          </div>

          <p className="mt-6 text-base leading-7 text-theme-muted text-center sm:text-left">
            Your identity has been authenticated against institutional records. You are now cleared for Shariah-compliant financing with premium credit access.
          </p>

          {/* Interactive Digital Verification Pass Passport Graphic */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.35 }}
            className="relative overflow-hidden rounded-[2rem] border border-white/10 bg-slate-950 p-6 shadow-2xl text-left max-w-md mx-auto sm:mx-0 mt-8 font-mono select-none"
            style={{
              backgroundImage: "radial-gradient(circle at 100% 0%, rgba(249, 115, 22, 0.15), transparent 45%), radial-gradient(circle at 0% 100%, rgba(52, 211, 153, 0.15), transparent 45%)"
            }}
          >
            {/* Card Header chip */}
            <div className="flex items-center justify-between mb-8">
              <span className="text-[9px] uppercase tracking-widest text-emerald-400 font-bold border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-0.5 rounded">
                SECURE IDENTITY PASS
              </span>
              <span className="text-white text-xs font-bold font-sans">SahulatKar</span>
            </div>

            {/* Card Chip & Scanner Graphic */}
            <div className="flex items-center justify-between mb-8">
              {/* Microchip */}
              <div className="w-10 h-8 bg-gradient-to-br from-amber-400 to-amber-600 rounded-lg relative overflow-hidden border border-amber-600/30">
                <div className="absolute top-1 bottom-1 left-2.5 right-2.5 border-x border-slate-950/20" />
                <div className="absolute left-1 right-1 top-2 bottom-2 border-y border-slate-950/20" />
              </div>
              <Sparkles className="h-6 w-6 text-emerald-400 animate-pulse" />
            </div>

            {/* Card Metadata */}
            <div className="space-y-4">
              <div>
                <p className="text-[8px] uppercase tracking-widest text-slate-500">Holder Name</p>
                <p className="text-sm font-bold text-white tracking-wide mt-1">{fullName}</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-[8px] uppercase tracking-widest text-slate-500">Document ID</p>
                  <p className="text-xs font-semibold text-slate-350 mt-1">CNIC: {cnic || "—"}</p>
                </div>
                <div>
                  <p className="text-[8px] uppercase tracking-widest text-slate-500">Status</p>
                  <p className="text-xs font-bold text-emerald-400 mt-1 flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 bg-emerald-500 rounded-full animate-ping" />
                    PLATINUM_OK
                  </p>
                </div>
              </div>
            </div>
          </motion.div>

          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            {[
              { label: "Security", value: "AES-256" },
              { label: "Credit Band", value: "AA+" },
              { label: "Status", value: "Active" },
            ].map((item, i) => (
              <motion.div
                key={item.label}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 + i * 0.08 }}
                className="rounded-2xl border border-[var(--section-border)] bg-[var(--card-bg)] p-4 text-center"
              >
                <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-theme-muted">{item.label}</p>
                <p className="mt-2 text-xl font-bold text-theme">{item.value}</p>
              </motion.div>
            ))}
          </div>

          <div className="mt-8 flex flex-col gap-4 sm:flex-row">
            <Button
              size="xl"
              className="w-full rounded-2xl bg-gradient-to-r from-orange-500 to-orange-600 py-6 shadow-lg shadow-orange-500/25 font-semibold text-white hover:from-orange-600 hover:to-orange-700"
              onClick={handleContinue}
            >
              Start Shopping
            </Button>
            <Button
              size="xl"
              variant="outline"
              className="w-full rounded-2xl border-[var(--section-border)] py-6 font-semibold"
              onClick={handleBack}
            >
              Back to Face Scan
            </Button>
          </div>
        </motion.section>

        {/* Right details panel card */}
        <motion.aside
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.1 }}
          className="capture-panel rounded-[2.5rem] p-8 shadow-[var(--shadow-soft)] border border-white/10 relative overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-tr from-orange-500/5 to-transparent pointer-events-none" />
          
          <div className="flex items-center justify-between gap-3 relative z-10">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-orange-300">Verification Status</p>
              <p className="mt-2 text-sm uppercase tracking-[0.2em] text-slate-400 font-medium">Level 3 — Platinum</p>
            </div>
            <div className="flex items-center gap-1 rounded-2xl bg-white/10 px-3 py-2">
              {[1, 2, 3, 4, 5].map((s) => (
                <Star key={s} className="h-3.5 w-3.5 fill-orange-400 text-orange-400" />
              ))}
            </div>
          </div>

          <div className="mt-10 space-y-6 text-slate-100 relative z-10">
            <div>
              <p className="text-[10px] uppercase tracking-[0.24em] text-slate-500">Verified Name</p>
              <p className="mt-3 text-2xl font-bold tracking-wide">{fullName}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.24em] text-slate-500">CNIC Number</p>
              <p className="mt-3 text-lg font-semibold tracking-widest font-mono text-slate-200">{cnic || "—"}</p>
            </div>
            
            {/* Redesigned glowing credit band card with a neon loader slider */}
            <div className="rounded-[1.5rem] border border-orange-400/20 bg-orange-500/10 p-5 relative overflow-hidden group">
              <div className="absolute -top-12 -right-12 w-28 h-28 rounded-full bg-orange-500/10 blur-xl group-hover:scale-150 transition-all duration-500" />
              <p className="text-[10px] uppercase tracking-[0.24em] text-orange-300 font-bold">Credit Band</p>
              <p className="mt-3 text-5xl font-black text-orange-200 tracking-wider">AA+</p>
              
              <div className="mt-4 flex items-center gap-3">
                <div className="h-1.5 flex-1 bg-slate-800 rounded-full overflow-hidden">
                  <motion.div 
                    initial={{ width: "0%" }}
                    animate={{ width: "95%" }}
                    transition={{ duration: 1.2, ease: "easeOut" }}
                    className="h-full bg-gradient-to-r from-orange-500 to-amber-400 rounded-full"
                  />
                </div>
                <span className="text-[9px] font-mono font-bold text-orange-300 uppercase tracking-wider">EXCELLENT</span>
              </div>
            </div>
          </div>

          <div className="mt-8 rounded-[1.5rem] border border-white/10 bg-white/5 p-5 text-sm relative z-10">
            <div className="flex items-center gap-2 text-orange-300">
              <Shield className="h-4 w-4" />
              <span className="font-semibold text-xs tracking-wider uppercase">Data encrypted with AES-256</span>
            </div>
            <p className="mt-3 text-slate-400 text-xs sm:text-sm leading-relaxed">
              Institutional-grade security protocols protect your identity information at every step.
            </p>
          </div>
        </motion.aside>
      </div>
    </VerificationPageShell>
  )
}
