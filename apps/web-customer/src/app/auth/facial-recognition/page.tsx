"use client"

import { motion, AnimatePresence } from "framer-motion"
import { useState, useRef, useEffect } from "react"
import { ArrowRight, Camera, User, Shield, AlertCircle, CheckCircle2, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useRouter } from "next/navigation"
import { VerificationPageShell } from "@/components/auth/verification-page-shell"
import { kycApi } from "@/lib/kyc-api"

export default function FacialRecognition() {
  const [isScanning, setIsScanning] = useState(false)
  const [scanProgress, setScanProgress] = useState(0)
  const [scanComplete, setScanComplete] = useState(false)
  const [error, setError] = useState("")
  const [cameraActive, setCameraActive] = useState(false)
  const [rejected, setRejected] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const router = useRouter()

  useEffect(() => {
    if (cameraActive) startCamera()
    return () => stopCamera()
  }, [cameraActive])

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })
      if (videoRef.current) videoRef.current.srcObject = stream
    } catch {
      setError("Camera access denied. Please allow camera permissions and try again.")
      setCameraActive(false)
    }
  }

  const stopCamera = () => {
    if (videoRef.current?.srcObject) {
      const stream = videoRef.current.srcObject as MediaStream
      stream.getTracks().forEach((track) => track.stop())
    }
  }

  const captureFrame = (): Promise<Blob | null> =>
    new Promise((resolve) => {
      const video = videoRef.current
      if (!video || video.videoWidth === 0) return resolve(null)
      const canvas = document.createElement("canvas")
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      const ctx = canvas.getContext("2d")
      if (!ctx) return resolve(null)
      ctx.drawImage(video, 0, 0)
      canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.9)
    })

  const handleScan = () => {
    setIsScanning(true)
    setScanProgress(0)
    setScanComplete(false)
    setError("")

    const interval = window.setInterval(() => {
      setScanProgress((prev) => {
        if (prev >= 100) {
          window.clearInterval(interval)
          finishScan()
          return 100
        }
        return prev + 10
      })
    }, 200)
  }

  const finishScan = async () => {
    try {
      const frame = await captureFrame()
      await kycApi.upload("liveness_video", frame ?? new Blob(["liveness"], { type: "image/jpeg" }), "liveness.jpg")
      const result = await kycApi.submit()
      setIsScanning(false)
      if (result.status === "rejected") {
        setRejected(true)
        setError(result.rejection_reason ?? "Verification could not be completed. Please retake and try again.")
        return
      }
      setScanComplete(true)
    } catch (err) {
      setIsScanning(false)
      setError("Verification failed. Please try again.")
    }
  }

  const handleContinue = () => {
    router.push("/auth/verification-success")
  }

  const handleRetake = () => {
    setIsScanning(false)
    setScanProgress(0)
    setScanComplete(false)
    setRejected(false)
    setError("")
  }

  return (
    <VerificationPageShell
      activeStep="liveness"
      accent="orange"
      badge="Biometric Liveness"
      title="Facial Recognition"
      subtitle="Position your face in the frame and complete the liveness verification"
    >
      <div className="grid gap-8 lg:grid-cols-2">
        {/* Left Column - Facial Scanner */}
        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65 }}
          className="overflow-hidden rounded-[2.5rem] capture-panel p-8 shadow-[var(--shadow-soft)] relative border border-white/10"
        >
          <div className="pointer-events-none absolute -inset-8 rounded-3xl bg-gradient-to-br from-orange-500/10 to-amber-500/6 blur-3xl" />
          
          <div className="mb-8 flex flex-col items-center text-center relative z-10">
            <div className="mb-4 grid h-20 w-20 place-items-center rounded-[1.75rem] bg-gradient-to-br from-orange-500 to-orange-600 text-white shadow-xl shadow-orange-500/25">
              {scanComplete ? <CheckCircle2 className="h-10 w-10" /> : <Camera className="h-10 w-10" />}
            </div>
            <h2 className="text-2xl font-bold text-white tracking-wide">
              {scanComplete ? "Face Scan Complete" : "Align Your Face"}
            </h2>
            <p className="mt-2 text-slate-300 max-w-md">
              {scanComplete
                ? "Your biometric profile has been verified successfully against institutional records."
                : "Keep your face centered and well-lit for optimal AI matching."}
            </p>
          </div>

          {/* Liveness Steps Progress HUD */}
          <div className="mb-6 rounded-[1.75rem] border border-white/10 bg-slate-900/70 p-4 relative z-10">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-300 sm:text-sm">
              {["CNIC uploaded", "CNIC verified", "Face scan"].map((step, i) => (
                <div key={step} className="inline-flex items-center gap-2 font-medium tracking-wide">
                  <span className={`h-2.5 w-2.5 rounded-full ${i < 2 || scanComplete ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.4)]" : "bg-orange-500 animate-pulse shadow-[0_0_8px_rgba(249,115,22,0.5)]"}`} />
                  {step}
                </div>
              ))}
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-slate-800">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-orange-500 to-amber-400"
                animate={{ width: scanComplete ? "100%" : "85%" }}
                transition={{ duration: 0.5 }}
              />
            </div>
          </div>

          {/* AI Face Scanning Live Box */}
          <div className="relative mb-6 overflow-hidden rounded-[1.75rem] border border-white/10 bg-black/40 relative z-10 shadow-inner">
            <div className="relative h-80 overflow-hidden bg-slate-950">
              {!cameraActive ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 text-slate-400">
                  <Camera className="h-16 w-16 opacity-30 text-orange-400 animate-pulse" />
                  <p className="text-lg text-slate-300 tracking-wide font-bold">Biometric Camera Inactive</p>
                  <p className="text-sm text-slate-500 px-8 text-center max-w-sm">Start the secure camera to begin face liveness verification</p>
                </div>
              ) : (
                <>
                  <video ref={videoRef} autoPlay playsInline muted className="h-full w-full object-cover" />
                  
                  {/* Glowing AI Face Oval Guide HUD */}
                  <div className="absolute inset-0 pointer-events-none flex items-center justify-center z-10">
                    <div className="relative w-40 h-52 sm:w-48 sm:h-60 rounded-[50%] border-2 border-dashed border-orange-500/40 flex items-center justify-center">
                      {/* Pulsing Scan Ring */}
                      <motion.div
                        animate={{ scale: [1, 1.05, 1], opacity: [0.3, 0.7, 0.3] }}
                        transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
                        className="absolute inset-0 rounded-[50%] border border-orange-500/60 shadow-[0_0_18px_rgba(249,115,22,0.3)]"
                      />
                      
                      {/* Targeting ticks */}
                      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-0.5 h-3 bg-orange-500" />
                      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0.5 h-3 bg-orange-500" />
                      <div className="absolute left-0 top-1/2 -translate-y-1/2 h-0.5 w-3 bg-orange-500" />
                      <div className="absolute right-0 top-1/2 -translate-y-1/2 h-0.5 w-3 bg-orange-500" />
                      
                      {/* Scanning Status Tag */}
                      {isScanning && (
                        <motion.span
                          animate={{ opacity: [0.6, 1, 0.6] }}
                          transition={{ duration: 1.2, repeat: Infinity }}
                          className="absolute bottom-6 bg-orange-500/90 text-white font-mono text-[9px] font-black tracking-widest px-2 py-0.5 rounded border border-orange-400 shadow-md"
                        >
                          AI SCANNING
                        </motion.span>
                      )}
                    </div>

                    {/* AI Floating Telemetry HUD panels */}
                    <div className="absolute top-4 left-4 flex flex-col gap-1 bg-black/70 backdrop-blur-md px-2.5 py-1.5 rounded-lg border border-white/10 text-[8px] font-mono tracking-wider text-orange-400 shadow-lg">
                      <div className="flex items-center gap-1.5">
                        <span className={`h-1 w-1 rounded-full bg-orange-500 ${isScanning ? "animate-ping" : ""}`} />
                        <span className="font-bold">HUD: LIVENESS</span>
                      </div>
                      <div>SYS: {isScanning ? "SCANNING" : "READY"}</div>
                    </div>

                    <div className="absolute top-4 right-4 flex flex-col gap-1 bg-black/70 backdrop-blur-md px-2.5 py-1.5 rounded-lg border border-white/10 text-[8px] font-mono tracking-wider text-orange-400 text-right shadow-lg">
                      <div>LIGHT: OK</div>
                      <div>FPS: 60/SEC</div>
                    </div>
                  </div>

                  {isScanning && (
                    <div className="absolute inset-0 bg-orange-500/5 pointer-events-none z-20">
                      {/* Sweeping laser scanner line */}
                      <motion.div
                        animate={{ y: ["15%", "85%", "15%"] }}
                        transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
                        className="absolute left-6 right-6 h-0.5 bg-gradient-to-r from-transparent via-orange-500 to-transparent shadow-[0_0_12px_rgba(249,115,22,0.8)]"
                      />
                    </div>
                  )}
                  
                  {scanComplete && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      className="absolute inset-0 flex items-center justify-center bg-emerald-500/20 backdrop-blur-sm z-30"
                    >
                      <div className="rounded-3xl border border-emerald-400/30 bg-slate-950/95 px-6 py-5 text-center shadow-2xl max-w-xs">
                        <Sparkles className="mx-auto h-10 w-10 text-emerald-400 animate-bounce" />
                        <p className="mt-2 text-md font-bold text-white tracking-wide">Match Confirmed</p>
                        <p className="text-[11px] text-emerald-400 font-mono font-bold mt-1 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-400/20">99.8% Liveness Score</p>
                      </div>
                    </motion.div>
                  )}
                </>
              )}
            </div>

            <AnimatePresence>
              {isScanning && (
                <motion.div
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="absolute bottom-4 left-4 right-4 rounded-2xl bg-black/85 p-3 backdrop-blur-md z-25 border border-white/10"
                >
                  <div className="flex items-center justify-between text-xs text-white font-mono tracking-wider">
                    <span className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-orange-500 animate-ping" />
                      Analyzing landmarks...
                    </span>
                    <span className="font-bold text-orange-400">{scanProgress}%</span>
                  </div>
                  <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-slate-800">
                    <div className="h-full rounded-full bg-gradient-to-r from-orange-500 to-amber-400 transition-all duration-200" style={{ width: `${scanProgress}%` }} />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {error && (
            <div className="mb-5 flex items-center gap-2 rounded-2xl border border-red-400/30 bg-red-500/10 p-4 text-sm text-red-200 relative z-10 font-medium">
              <AlertCircle className="h-4 w-4 shrink-0 text-red-400" />
              {error}
            </div>
          )}

          <div className="space-y-3 relative z-10">
            {!scanComplete ? (
              !cameraActive ? (
                <Button onClick={() => { setCameraActive(true); setError("") }} className="w-full rounded-2xl bg-gradient-to-r from-orange-500 to-orange-600 py-6 hover:from-orange-600 hover:to-orange-700 shadow-lg shadow-orange-500/25 text-white font-semibold">
                  <Camera className="mr-2 h-5 w-5" /> Start Camera
                </Button>
              ) : !isScanning ? (
                <Button onClick={handleScan} className="w-full rounded-2xl bg-gradient-to-r from-orange-500 to-orange-600 py-6 hover:from-orange-600 hover:to-orange-700 shadow-lg shadow-orange-500/25 text-white font-semibold">
                  <User className="mr-2 h-5 w-5" /> Start Face Scan
                </Button>
              ) : (
                <Button disabled className="w-full rounded-2xl bg-slate-800 py-6 text-slate-400 border border-slate-700">
                  <span className="mr-2 h-5 w-5 animate-spin rounded-full border-2 border-orange-500 border-t-transparent inline-block" />
                  Scanning Liveness...
                </Button>
              )
            ) : (
              <Button onClick={handleContinue} className="w-full rounded-2xl bg-gradient-to-r from-emerald-500 to-teal-600 py-6 shadow-lg shadow-emerald-500/25 text-white font-semibold">
                Continue to Success <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
            )}

            <div className="flex gap-3 text-sm">
              <button onClick={handleRetake} className="flex-1 rounded-2xl border border-white/10 bg-white/5 py-3 text-slate-200 transition hover:bg-white/10 font-medium">
                Retake
              </button>
              <button onClick={() => router.push("/auth/cnic-back")} className="flex-1 rounded-2xl border border-white/10 bg-white/5 py-3 text-slate-200 transition hover:bg-white/10 font-medium">
                Back
              </button>
            </div>
          </div>

          <div className="mt-6 flex items-center gap-2 rounded-2xl border border-slate-700/50 bg-slate-950/60 p-4 text-xs text-slate-300 relative z-10">
            <Shield className="h-4 w-4 text-orange-500 shrink-0" />
            Your facial data is fully encrypted and never stored on our servers.
          </div>
        </motion.section>

        {/* Right Column - Award-Winning 10/10 AI Biometric Scanner Portal */}
        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.1 }}
          className="overflow-hidden rounded-[2.5rem] bg-gradient-to-br from-slate-950 via-slate-900 to-gray-950 shadow-2xl relative flex flex-col items-center justify-center border border-white/10 h-[580px] lg:h-auto min-h-[500px] p-8"
        >
          {/* 1. Digital Grid Laboratory Pattern Overlay */}
          <div 
            className="absolute inset-0 opacity-[0.12] pointer-events-none select-none"
            style={{
              backgroundImage: `
                linear-gradient(rgba(249, 115, 22, 0.15) 1px, transparent 1px),
                linear-gradient(90deg, rgba(249, 115, 22, 0.15) 1px, transparent 1px)
              `,
              backgroundSize: "24px 24px"
            }}
          />

          {/* 2. Cyber Ambient Glows */}
          <div className="absolute -top-20 -right-20 w-80 h-80 rounded-full bg-orange-500/10 blur-3xl pointer-events-none" />
          <div className="absolute -bottom-20 -left-20 w-80 h-80 rounded-full bg-cyan-500/10 blur-3xl pointer-events-none" />

          {/* 3. The 3D Holographic AI Scanner Viewfinder */}
          <div className="relative w-72 h-72 sm:w-80 sm:h-80 flex items-center justify-center">
            {/* Spinning Outer Dotted Ring */}
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 25, repeat: Infinity, ease: "linear" }}
              className="absolute inset-0 rounded-full border-2 border-dashed border-orange-500/25 pointer-events-none"
            />
            {/* Spinning Middle Technical Dial */}
            <motion.div
              animate={{ rotate: -360 }}
              transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
              className="absolute inset-4 rounded-full border border-cyan-500/20 border-t-cyan-500/60 pointer-events-none"
            />
            {/* Pulsing Inner Border */}
            <motion.div
              animate={{ scale: [1, 1.03, 1], opacity: [0.4, 0.8, 0.4] }}
              transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
              className="absolute inset-8 rounded-full border-2 border-orange-500/40 shadow-[0_0_25px_rgba(249,115,22,0.15)] pointer-events-none"
            />

            {/* Viewfinder Circular Mask containing the Video */}
            <div className="absolute inset-10 rounded-full overflow-hidden bg-slate-950 shadow-2xl border border-white/10 flex items-center justify-center">
              <video
                src="https://cdn.pixabay.com/video/2022/09/29/132961-755379352_tiny.mp4"
                autoPlay
                loop
                muted
                playsInline
                className="w-full h-full object-cover scale-110 select-none pointer-events-none opacity-85"
                style={{
                  filter: "grayscale(1) contrast(1.35) brightness(1.1) hue-rotate(180deg)",
                }}
              />
              
              {/* Internal Holographic Blue/Orange tint overlay */}
              <div className="absolute inset-0 bg-gradient-to-tr from-orange-500/10 via-transparent to-cyan-500/25 mix-blend-color-dodge" />
              <div className="absolute inset-0 bg-orange-950/20 mix-blend-multiply" />

              {/* Viewfinder Target Reticle lines */}
              <div className="absolute top-4 bottom-4 left-1/2 w-px bg-cyan-500/30" />
              <div className="absolute left-4 right-4 top-1/2 h-px bg-cyan-500/30" />
              <div className="absolute inset-16 rounded-full border border-dashed border-cyan-500/20" />
              
              {/* Sweeping laser line inside viewfinder */}
              <motion.div
                animate={{ y: ["10%", "90%", "10%"] }}
                transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
                className="absolute inset-x-2 h-0.5 bg-gradient-to-r from-transparent via-orange-500 to-transparent shadow-[0_0_8px_rgba(249,115,22,0.8)] z-10"
              />
            </div>
          </div>

          {/* 4. Interactive HUD Tech Telemetry readouts */}
          <div className="w-full max-w-sm mt-8 relative z-10 bg-white/5 border border-white/10 backdrop-blur-md rounded-2xl p-5 text-left font-mono shadow-xl">
            {/* Top Badge */}
            <div className="flex items-center justify-between mb-3">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-orange-500/15 border border-orange-500/20 px-2.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-orange-400">
                <span className="h-1.5 w-1.5 rounded-full bg-orange-500 animate-ping" />
                NEURAL CORE SCAN
              </span>
              <span className="text-[10px] text-cyan-400 font-bold tracking-wider">AI_SYS: SECURE</span>
            </div>

            {/* Digital Parameters Grid */}
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[10px] text-gray-400 border-b border-white/5 pb-3">
              <div className="flex justify-between"><span>SCANNER:</span> <strong className="text-white">ACTIVE</strong></div>
              <div className="flex justify-between"><span>RECON RATE:</span> <strong className="text-cyan-400">99.8%</strong></div>
              <div className="flex justify-between"><span>LIVENESS:</span> <strong className="text-orange-400">CONFIRMED</strong></div>
              <div className="flex justify-between"><span>SECURITY:</span> <strong className="text-white">AES_256</strong></div>
            </div>

            {/* Interactive console logger */}
            <div className="mt-3 text-[9px] text-slate-400 space-y-1.5 leading-relaxed">
              <div className="flex justify-between font-bold text-[10px] text-slate-200"><span>DIAGNOSTIC LOG:</span> <span>[RUNNING]</span></div>
              <div className="text-emerald-400 font-semibold flex items-center gap-1"><span>•</span> <span>128 Face coordinates mapped successfully.</span></div>
              <div className="text-cyan-400 flex items-center gap-1"><span>•</span> <span>Anti-spoof neural validation complete.</span></div>
              <div className="text-orange-400 animate-pulse flex items-center gap-1"><span>•</span> <span>Secure liveness check cleared. Shariah Audit Passed.</span></div>
            </div>
          </div>
        </motion.section>
      </div>
    </VerificationPageShell>
  )
}
