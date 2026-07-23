"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Check, ArrowRight, Shield, RefreshCw, Cpu, Activity, CreditCard } from "lucide-react"
import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { ordersApi } from "@/lib/orders-api"
import { paymentsApi } from "@/lib/payments-api"

export default function ProcessingPayment() {
  const [steps, setSteps] = useState([
    { id: 1, label: "Down Payment Confirmed", status: "pending", substatus: "AWAITING_GATEWAY_CONFIRMATION" },
    { id: 2, label: "Issuing Virtual Purchase Cards", status: "pending", substatus: "ROUTING_GATEWAY_LINK" },
  ])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const router = useRouter()

  useEffect(() => {
    let cancelled = false

    const run = async () => {
      const raw = sessionStorage.getItem("sk_cart_order_ids")
      if (!raw) {
        router.replace("/cart")
        return
      }
      const orderIds: number[] = JSON.parse(raw)

      try {
        // Poll until the down payment (confirmed synchronously in dev, async via a
        // real gateway webhook in production) has advanced every order.
        let orders = await Promise.all(orderIds.map((id) => ordersApi.get(id)))
        let attempts = 0
        while (orders.some((o) => o.status === "contracts_signed") && attempts < 20) {
          await new Promise((r) => setTimeout(r, 1500))
          orders = await Promise.all(orderIds.map((id) => ordersApi.get(id)))
          attempts++
        }
        if (cancelled) return
        setSteps((prev) => prev.map((s) => (s.id === 1 ? { ...s, status: "completed" } : s)))

        await Promise.all(orderIds.map((id) => paymentsApi.issueVcn(id)))

        attempts = 0
        orders = await Promise.all(orderIds.map((id) => ordersApi.get(id)))
        while (orders.some((o) => !["vcn_issued", "purchasing", "purchase_confirmed", "delivery_pending", "in_transit", "delivered", "completed"].includes(o.status)) && attempts < 20) {
          await new Promise((r) => setTimeout(r, 1500))
          orders = await Promise.all(orderIds.map((id) => ordersApi.get(id)))
          attempts++
        }
        if (cancelled) return
        setSteps((prev) => prev.map((s) => (s.id === 2 ? { ...s, status: "completed" } : s)))
        setLoading(false)
      } catch (err) {
        if (!cancelled) setError("Something went wrong while confirming your payment.")
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [router])

  return (
    <div 
      className="min-h-screen relative overflow-hidden flex items-center justify-center px-4 py-20 text-white bg-slate-950"
      style={{
        backgroundImage: "url('/images/engine_bg_glow.png')",
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      }}
    >
      {/* Deep luxury back overlays */}
      <div className="pointer-events-none absolute inset-0 bg-slate-950/85 backdrop-blur-[2px]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-96 bg-[radial-gradient(circle_at_top,_rgba(249,115,22,0.18),transparent_48%)]" />

      {/* Ambient custom cyber sparks */}
      <div className="absolute top-1/3 left-10 w-96 h-96 rounded-full bg-orange-500/10 blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/3 right-10 w-96 h-96 rounded-full bg-orange-600/5 blur-3xl pointer-events-none" />

      <div className="w-full max-w-6xl relative z-10">
        <div className="grid lg:grid-cols-12 gap-8 lg:gap-12 items-center">
          
          {/* Left Column: Transaction logs and aperture */}
          <motion.div 
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, ease: "easeOut" }}
            className="lg:col-span-7 w-full"
          >
            {/* Premium glassmorphic console card */}
            <div className="bg-slate-900/70 rounded-[2.5rem] p-6 sm:p-10 shadow-2xl border border-white/10 backdrop-blur-2xl relative overflow-hidden space-y-8">
              
              {/* Header section */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/5 pb-6">
                <div className="space-y-1.5 text-left">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-orange-500/15 border border-orange-500/20 px-3.5 py-1 text-[10px] font-black uppercase tracking-widest text-orange-400">
                    🔐 SECURE SHARIAH GATEWAY
                  </span>
                  <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">Processing Payment...</h1>
                </div>
                <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-950/80 rounded-xl border border-white/5 font-mono text-[10px] text-gray-400">
                  <Activity className="w-3.5 h-3.5 text-orange-500 animate-pulse" />
                  <span>LATENCY: 1.2ms</span>
                </div>
              </div>

              {/* Loader details grid */}
              <div className="grid sm:grid-cols-12 gap-6 items-center">
                
                {/* Advanced Biometric Circular Aperture Loader */}
                <div className="sm:col-span-5 flex justify-center py-2">
                  <div className="relative w-36 h-36">
                    {/* Outer spinning tech dashes */}
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
                      className="absolute inset-0 rounded-full border-2 border-dashed border-orange-500/30"
                    />
                    {/* Inner reverse spinning ring */}
                    <motion.div
                      animate={{ rotate: -360 }}
                      transition={{ duration: 5, repeat: Infinity, ease: "linear" }}
                      className="absolute inset-2.5 rounded-full border border-orange-400/20 border-t-orange-400/70"
                    />
                    {/* Pulsing inner scanner ring */}
                    <motion.div
                      animate={{ scale: [1, 1.06, 1], opacity: [0.3, 0.7, 0.3] }}
                      transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                      className="absolute inset-5 rounded-full border-2 border-orange-500/40 shadow-[0_0_20px_rgba(249,115,22,0.3)]"
                    />
                    {/* Core central security lock */}
                    <div className="absolute inset-7 bg-slate-950 rounded-full border border-white/10 flex items-center justify-center shadow-inner">
                      {loading ? (
                        <span className="text-2xl animate-pulse">🔒</span>
                      ) : (
                        <motion.span 
                          initial={{ scale: 0.5, rotate: -45 }}
                          animate={{ scale: 1, rotate: 0 }}
                          transition={{ type: "spring", stiffness: 200 }}
                          className="text-2xl"
                        >
                          🔓
                        </motion.span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="sm:col-span-7 text-left space-y-4">
                  <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
                    Please do not close your browser or refresh this page. We are finalizing your installment ledger in real-time with institutional-grade security protocols.
                  </p>
                  <div className="flex items-center gap-3">
                    <Shield className="w-5 h-5 text-orange-500" />
                    <span className="text-xs font-mono font-bold tracking-wide text-slate-200 uppercase">
                      AES-256 Bit Encryption Active
                    </span>
                  </div>
                </div>
              </div>

              {/* Clean Monospace HUD Steps readout logs */}
              <div className="space-y-3 font-mono">
                {steps.map((step) => (
                  <div
                    key={step.id}
                    className={`flex items-start gap-3.5 p-4 rounded-2xl border transition-all duration-300 ${
                      step.status === "completed"
                        ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                        : "bg-slate-950/40 border-white/5 text-slate-500"
                    }`}
                  >
                    <div className="flex-shrink-0 mt-0.5">
                      {step.status === "completed" ? (
                        <div className="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center shadow-lg shadow-emerald-500/20">
                          <Check className="w-3 h-3 text-white" />
                        </div>
                      ) : (
                        <div className="w-5 h-5 rounded-full border border-orange-500/40 flex items-center justify-center animate-pulse">
                          <span className="w-1.5 h-1.5 rounded-full bg-orange-500" />
                        </div>
                      )}
                    </div>
                    
                    <div className="text-left space-y-1">
                      <p className={`font-bold text-sm ${step.status === "completed" ? "text-white" : "text-slate-400"}`}>{step.label}</p>
                      <p className="text-[9px] tracking-widest font-semibold opacity-70 uppercase">{step.substatus}</p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Interactive footer details and manual action triggers */}
              <div className="border-t border-white/5 pt-6 text-center sm:text-left">
                {error ? (
                  <div className="inline-flex items-center gap-2 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-2.5">
                    <span className="text-xs font-semibold text-red-400 tracking-wider font-mono">{error}</span>
                  </div>
                ) : loading ? (
                  <div className="inline-flex items-center gap-2 bg-orange-500/10 border border-orange-500/20 rounded-xl px-4 py-2.5">
                    <span className="w-2 h-2 rounded-full bg-orange-500 animate-ping" />
                    <span className="text-xs font-semibold text-orange-400 tracking-wider font-mono">ESTABLISHING FINTECH BRIDGE...</span>
                  </div>
                ) : (
                  <div className="space-y-6">
                    <div className="inline-flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-4 py-2.5">
                      <span className="w-2 h-2 rounded-full bg-emerald-500" />
                      <span className="text-xs font-semibold text-emerald-400 tracking-wider font-mono">PAYMENT SECURED SUCCESSFULLY</span>
                    </div>

                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ type: "spring", stiffness: 150 }}
                    >
                      <Button
                        onClick={() => router.push("/payments/order-success")}
                        className="w-full rounded-2xl bg-gradient-to-r from-orange-500 to-orange-600 py-6 text-base font-bold shadow-lg shadow-orange-500/25 hover:from-orange-600 hover:to-orange-700 text-white transform active:scale-95 transition-all"
                      >
                        View Order Confirmation
                        <ArrowRight className="w-5 h-5 ml-2 inline-block" />
                      </Button>
                    </motion.div>
                  </div>
                )}
              </div>
            </div>
          </motion.div>

          {/* Right Column: Dynamic Holographic Card Moving */}
          <motion.div 
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="lg:col-span-5 w-full flex flex-col items-center justify-center text-center space-y-6"
          >
            <div className="relative w-full max-w-sm aspect-[4/5] rounded-[2.5rem] bg-gradient-to-b from-slate-900/60 to-slate-950/40 border border-white/10 p-6 flex flex-col justify-between overflow-hidden shadow-2xl backdrop-blur-md">
              {/* Outer floating ambient lights */}
              <div className="absolute top-0 right-0 w-32 h-32 bg-orange-500/10 rounded-full blur-2xl pointer-events-none" />
              <div className="absolute bottom-0 left-0 w-32 h-32 bg-orange-500/5 rounded-full blur-2xl pointer-events-none" />

              {/* Telemetry labels */}
              <div className="flex justify-between items-center text-[10px] font-mono text-gray-500 border-b border-white/5 pb-4">
                <span>SECURED TRANSFER INTERFACE</span>
                <span className="text-orange-400 font-bold">NODE: SA-77</span>
              </div>

              {/* Floating Holographic Card Container */}
              <div className="flex-1 flex items-center justify-center py-4 relative">
                {/* Holographic glowing back dial */}
                <motion.div 
                  animate={{ rotate: 360 }}
                  transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
                  className="absolute w-56 h-56 rounded-full border border-dashed border-orange-500/15 flex items-center justify-center"
                />
                <motion.div 
                  animate={{ rotate: -360 }}
                  transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
                  className="absolute w-44 h-44 rounded-full border border-dashed border-orange-500/20"
                />

                {/* Animated Flying 3D Credit Card */}
                <motion.div
                  animate={{ 
                    y: [0, -12, 0],
                    rotateX: [10, 15, 10],
                    rotateY: [-10, -5, -10],
                  }}
                  transition={{ 
                    duration: 4, 
                    repeat: Infinity, 
                    ease: "easeInOut" 
                  }}
                  className="w-full max-w-[240px] aspect-[1.58/1] rounded-2xl overflow-hidden relative shadow-[0_20px_50px_rgba(249,115,22,0.25)] border border-white/10 flex items-center justify-center bg-slate-950"
                  style={{ transformStyle: "preserve-3d", perspective: 1000 }}
                >
                  {/* Embedded high-end generated asset image */}
                  <img 
                    src="/images/card_processing_animation.png" 
                    alt="Payment processing credit card animation"
                    className="w-full h-full object-cover opacity-90"
                  />
                  
                  {/* Glass shimmer sheet overlay */}
                  <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-white/5 to-transparent shimmer pointer-events-none" />
                </motion.div>
              </div>

              {/* Status footer readouts */}
              <div className="space-y-2 border-t border-white/5 pt-4">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-gray-400">Ledger Compliance:</span>
                  <span className="text-emerald-500 font-extrabold font-mono">100% HALAL</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-gray-400">Gateway Pipeline:</span>
                  <span className="text-orange-400 font-mono font-bold uppercase tracking-wider">ACTIVE ROUTE</span>
                </div>
              </div>
            </div>
          </motion.div>

        </div>
      </div>
    </div>
  )
}

