"use client"

import { motion } from "framer-motion"
import { useRef, useState } from "react"
import { ArrowRight, Camera, CheckCircle2, ChevronLeft, ChevronRight, ScanLine, Shield, Upload, Cpu, Activity, Info } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useRouter } from "next/navigation"
import { VerificationPageShell } from "@/components/auth/verification-page-shell"
import { kycApi } from "@/lib/kyc-api"

export default function CNICBack() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState("")
  const fileInputRef = useRef<HTMLInputElement>(null)
  const router = useRouter()

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith("image/")) {
      setError("Please upload a valid image file.")
      return
    }
    const reader = new FileReader()
    reader.onload = (uploadEvent) => setPreview(uploadEvent.target?.result as string)
    reader.readAsDataURL(file)
    setSelectedFile(file)
    setError("")
  }

  const handleSubmit = async () => {
    if (!selectedFile) {
      setError("Please upload the CNIC back image before continuing.")
      return
    }
    setIsLoading(true)
    setError("")
    try {
      await kycApi.upload("cnic_back", selectedFile, selectedFile.name)
      router.push("/auth/facial-recognition")
    } catch (err) {
      setError("Could not upload this image. Please try again.")
      setIsLoading(false)
    }
  }

  return (
    <VerificationPageShell
      activeStep="cnic-back"
      accent="orange"
      badge="MRZ Scanning"
      title="Capture CNIC Back"
      subtitle="Scan the back of your card to extract MRZ data and verify security features"
    >
      <div className="grid gap-8 xl:grid-cols-[1.65fr_1fr]">
        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65 }}
          className="overflow-hidden rounded-[2.5rem] capture-panel p-6 shadow-[var(--shadow-soft)]"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="inline-flex items-center gap-2 rounded-full border border-orange-400/25 bg-orange-500/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-orange-200">
              <ScanLine className="h-3.5 w-3.5 text-orange-400 animate-pulse" />
              Live scanning
            </span>
            <div className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 p-1">
              <button type="button" className="rounded-full p-2 text-slate-200 transition hover:bg-white/10">
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button type="button" className="rounded-full p-2 text-slate-200 transition hover:bg-white/10">
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div
            onClick={() => fileInputRef.current?.click()}
            className="group relative mt-6 cursor-pointer overflow-hidden rounded-[2rem] border border-white/10 bg-slate-900/70 p-5 transition hover:border-orange-400/30"
          >
            <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileSelect} className="hidden" />
            <div className="relative aspect-[16/10] overflow-hidden rounded-[1.5rem] border border-white/10 bg-slate-950">
              {preview ? (
                <img src={preview} alt="CNIC Back Preview" className="h-full w-full object-cover" />
              ) : (
                <div className="grid h-full place-items-center px-6 text-center text-slate-300 relative overflow-hidden">
                  <div className="absolute top-1/4 right-1/4 w-40 h-40 rounded-full bg-orange-500/10 blur-3xl pointer-events-none" />
                  <div className="absolute bottom-1/4 left-1/4 w-40 h-40 rounded-full bg-orange-600/5 blur-3xl pointer-events-none" />

                  {/* Card Back template outline */}
                  <div className="absolute inset-8 rounded-2xl border border-white/5 bg-slate-900/40 backdrop-blur-sm p-5 flex flex-col justify-between text-left select-none pointer-events-none shadow-2xl">
                    <div className="flex justify-between items-start">
                      <div className="space-y-1">
                        <div className="w-20 h-1.5 bg-white/5 rounded" />
                        <div className="w-14 h-1 bg-white/5 rounded" />
                      </div>
                      <div className="w-14 h-6 rounded bg-slate-950/60 border border-white/10 flex items-center justify-center">
                        <div className="w-10 h-2 bg-white/15 rounded" />
                      </div>
                    </div>

                    <div className="space-y-2.5 my-2">
                      <div className="w-32 h-1.5 bg-white/5 rounded" />
                      <div className="w-44 h-1 bg-white/5 rounded" />
                    </div>

                    {/* Bottom MRZ lines */}
                    <div className="border-t border-white/5 pt-2.5 space-y-1.5 font-mono text-[7px] sm:text-[9px] tracking-widest text-slate-500">
                      <div>IDPAK&lt;0D12345678&lt;9PAK0000001&lt;&lt;&lt;&lt;&lt;</div>
                      <div>AHMED&lt;&lt;MOHAMMAD&lt;E&lt;RASHID&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;</div>
                    </div>
                  </div>

                  <div className="space-y-5 z-10 relative mt-4 bg-slate-950/80 p-6 rounded-2xl border border-white/10 backdrop-blur-md max-w-xs shadow-xl">
                    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-orange-500/30 bg-orange-500/10 shadow-lg text-orange-400">
                      <Camera className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-base font-bold text-white">Capture CNIC Back</p>
                      <p className="mt-1 text-xs text-slate-400">Scan card back to parse MRZ telemetry</p>
                    </div>
                  </div>
                </div>
              )}
              {/* Dynamic laser scan line */}
              <motion.div
                animate={{ y: ["12%", "88%", "12%"] }}
                transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }}
                className="pointer-events-none absolute left-6 right-6 h-0.5 bg-gradient-to-r from-transparent via-orange-500 to-transparent shadow-[0_0_12px_rgba(249,115,22,0.8)] z-20"
              />
            </div>
            <div className="pointer-events-none absolute bottom-8 left-8 right-8 rounded-2xl border border-white/10 bg-slate-950/80 p-4 text-xs text-slate-300 backdrop-blur-md">
              Position the back of your CNIC within the frame for auto-capture.
            </div>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <Button
              type="button"
              variant="outline"
              className="inline-flex items-center gap-2 rounded-2xl border-white/15 bg-white/5 px-5 py-3 text-white hover:bg-white/10"
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="h-4 w-4" />
              Upload Image
            </Button>
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
              <CheckCircle2 className="h-4 w-4" />
              Front image captured
            </div>
          </div>
        </motion.section>

        <motion.aside
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.08 }}
          className="theme-panel rounded-[2.5rem] p-8 shadow-[var(--shadow-soft)] text-left"
        >
          <div className="flex items-center justify-between gap-4 border-b border-gray-100 dark:border-white/5 pb-4">
            <div>
              <p className="text-[10px] font-extrabold uppercase tracking-[0.28em] text-theme-muted">Data Extraction</p>
              <p className="mt-1 text-xs font-bold uppercase tracking-[0.2em] text-theme">Real-time parsing</p>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-2xl bg-orange-500/10 border border-orange-500/20 px-3.5 py-1.5 text-xs font-bold text-orange-500">
              <Shield className="h-4 w-4" /> Verified
            </span>
          </div>

          <div className="mt-8 space-y-4">
            <div className="rounded-[1.5rem] border border-[var(--section-border)] bg-[var(--card-bg)] p-5 relative overflow-hidden group">
              <p className="text-[9px] font-extrabold uppercase tracking-[0.24em] text-theme-muted">MRZ Machine readable zone</p>
              <pre className="mt-3 whitespace-pre-wrap font-mono text-xs leading-relaxed text-theme sm:text-sm group-hover:text-orange-500 transition-colors">
                {"IDPAK<0D12345678<9PAK0000001<<<<<\nAHMED<<MOHAMMAD<E<RASHID<<<<<<<<<<<<<<"}
              </pre>
            </div>
            <div className="rounded-[1.5rem] border border-[var(--section-border)] bg-[var(--card-bg)] p-5 flex justify-between items-center gap-4 hover:border-orange-500/20 transition duration-300">
              <div className="space-y-1">
                <p className="text-[9px] font-extrabold uppercase tracking-[0.24em] text-theme-muted">Permanent Address</p>
                <p className="text-sm text-theme font-bold">House No. 124, Sector F-10/2, Islamabad, ICT, Pakistan</p>
              </div>
              <div className="w-10 h-10 rounded-xl bg-orange-500/10 border border-orange-500/20 flex items-center justify-center text-orange-500">
                <Info className="w-4 h-4" />
              </div>
            </div>
            <div className="rounded-[1.5rem] border border-orange-200/60 bg-orange-50/80 p-5 dark:border-orange-500/20 dark:bg-orange-500/10 flex gap-3">
              <Shield className="w-5 h-5 text-orange-500 mt-0.5 flex-shrink-0 animate-pulse" />
              <div>
                <p className="font-extrabold text-orange-700 dark:text-orange-300 text-sm">Micro-text Verified</p>
                <p className="mt-1 text-xs text-theme-muted leading-relaxed">Security features confirmed through automated MRZ scanning.</p>
              </div>
            </div>
            <div className="rounded-[1.5rem] border border-[var(--section-border)] bg-[var(--card-bg)] p-5 flex justify-between items-center">
              <div>
                <p className="text-[9px] font-extrabold uppercase tracking-[0.24em] text-theme-muted">Extraction Confidence</p>
                <p className="mt-2 text-3xl font-black text-theme">98.4%</p>
              </div>
              <div className="w-12 h-12 bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-500 rounded-xl">
                <Activity className="w-5 h-5" />
              </div>
            </div>
          </div>

          {error && (
            <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
              {error}
            </div>
          )}

          <Button
            size="xl"
            className="mt-8 w-full rounded-2xl bg-gradient-to-r from-orange-500 to-orange-600 py-6 shadow-lg shadow-orange-500/25 btn-smooth"
            onClick={handleSubmit}
            disabled={isLoading}
          >
            {isLoading ? "Continuing..." : "Continue to Liveness"}
            <ArrowRight className="h-5 w-5" />
          </Button>
        </motion.aside>
      </div>
    </VerificationPageShell>
  )
}

