"use client"

import { motion } from "framer-motion"
import { useEffect, useRef, useState } from "react"
import { ArrowRight, Camera, CheckCircle2, RefreshCcw, ScanLine, Upload, User, FileText, Cpu, Shield, Clock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useRouter } from "next/navigation"
import { VerificationPageShell } from "@/components/auth/verification-page-shell"
import { kycApi } from "@/lib/kyc-api"

export default function CNICFront() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState("")
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const router = useRouter()

  useEffect(() => {
    kycApi.start().catch(() => {})
  }, [])

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    processFile(file)
  }

  const processFile = (file: File) => {
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

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const handleSubmit = async () => {
    if (!selectedFile) {
      setError("Please upload the CNIC front image before continuing.")
      return
    }
    setIsLoading(true)
    setError("")
    try {
      await kycApi.upload("cnic_front", selectedFile, selectedFile.name)
      router.push("/auth/cnic-back")
    } catch (err) {
      setError("Could not upload this image. Please try again.")
      setIsLoading(false)
    }
  }

  return (
    <VerificationPageShell
      activeStep="cnic-front"
      accent="orange"
      badge="Document Capture"
      title="Capture CNIC Front"
      subtitle="Upload or scan the front of your national identity card for instant verification"
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
              Live camera feed
            </span>
            <button
              type="button"
              onClick={() => { setSelectedFile(null); setPreview(null) }}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition hover:bg-white/10"
            >
              <RefreshCcw className="h-4 w-4" />
              Retake Photo
            </button>
          </div>

          <div
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setIsDragging(false)
              const file = e.dataTransfer.files?.[0]
              if (file) processFile(file)
            }}
            className={`group relative mt-6 cursor-pointer overflow-hidden rounded-[2rem] border-2 border-dashed p-5 transition-all duration-300 ${
              isDragging
                ? "border-orange-450 bg-orange-500/10"
                : "border-white/15 bg-slate-900/60 hover:border-orange-400/40"
            }`}
          >
            <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileSelect} className="hidden" />
            <div className="relative aspect-[16/10] overflow-hidden rounded-[1.5rem] border border-white/10 bg-slate-950">
              {preview ? (
                <img src={preview} alt="CNIC Front Preview" className="h-full w-full object-cover" />
              ) : (
                <div className="grid h-full place-items-center px-6 text-center text-slate-300 relative overflow-hidden">
                  
                  {/* Glowing background highlights */}
                  <div className="absolute top-1/4 left-1/4 w-40 h-40 rounded-full bg-orange-500/5 blur-3xl pointer-events-none" />
                  <div className="absolute bottom-1/4 right-1/4 w-40 h-40 rounded-full bg-emerald-500/5 blur-3xl pointer-events-none" />

                  {/* High-end virtual simulated card template outline */}
                  <div className="absolute inset-8 rounded-2xl border border-white/5 bg-slate-900/40 backdrop-blur-sm p-5 flex flex-col justify-between text-left select-none pointer-events-none shadow-2xl">
                    <div className="flex justify-between items-start">
                      <div className="space-y-1">
                        <div className="w-16 h-2 bg-white/10 rounded" />
                        <div className="w-24 h-1.5 bg-white/5 rounded" />
                      </div>
                      <div className="w-6 h-6 rounded bg-gradient-to-br from-amber-400 to-amber-500 opacity-60 flex items-center justify-center">
                        <Cpu className="w-3.5 h-3.5 text-amber-900" />
                      </div>
                    </div>

                    {/* Middle: simulated photo avatar frame */}
                    <div className="flex items-center space-x-4 my-2">
                      <div className="w-12 h-16 rounded border border-white/10 bg-slate-950 flex items-center justify-center">
                        <User className="w-6 h-6 text-white/20" />
                      </div>
                      <div className="space-y-2 flex-1">
                        <div className="w-28 h-2 bg-white/10 rounded" />
                        <div className="w-36 h-1.5 bg-white/5 rounded" />
                        <div className="w-20 h-1.5 bg-white/5 rounded" />
                      </div>
                    </div>

                    <div className="flex justify-between items-center border-t border-white/5 pt-2">
                      <div className="w-28 h-1.5 bg-white/5 rounded" />
                      <div className="w-8 h-2 bg-emerald-500/20 rounded border border-emerald-500/30" />
                    </div>
                  </div>

                  <div className="space-y-5 z-10 relative mt-6 bg-slate-950/80 p-6 rounded-2xl border border-white/10 backdrop-blur-md max-w-xs shadow-xl">
                    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-orange-500/30 bg-orange-500/10 shadow-lg text-orange-400">
                      <Camera className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-base font-bold text-white">Capture CNIC Front</p>
                      <p className="mt-1 text-xs text-slate-400">Drag & drop or tap to trigger camera capture</p>
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
              <div className="pointer-events-none absolute inset-6 rounded-[1.25rem] border border-orange-400/20" />
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
              CNIC verification is live
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
              <p className="text-[10px] font-extrabold uppercase tracking-[0.28em] text-theme-muted">Document Status</p>
              <p className="mt-1 text-xs font-bold uppercase tracking-[0.2em] text-theme-muted">
                {selectedFile ? "Awaiting verification" : "No document yet"}
              </p>
            </div>
            {selectedFile ? (
              <span className="inline-flex items-center gap-1.5 rounded-2xl bg-amber-500/10 border border-amber-500/20 px-3.5 py-1.5 text-xs font-bold text-amber-600 dark:text-amber-400">
                <Clock className="h-3.5 w-3.5" /> Under Review
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-2xl bg-slate-500/10 border border-slate-500/20 px-3.5 py-1.5 text-xs font-bold text-slate-500 dark:text-slate-400">
                Not Uploaded
              </span>
            )}
          </div>

          <div className="mt-8 space-y-4">
            {selectedFile ? (
              <div className="rounded-[1.5rem] border border-[var(--section-border)] bg-[var(--card-bg)] p-5 shadow-sm flex items-center justify-between gap-4 hover:border-orange-500/20 transition duration-300 group">
                <div className="space-y-1 overflow-hidden">
                  <p className="text-[9px] font-extrabold uppercase tracking-[0.24em] text-theme-muted">File Selected</p>
                  <p className="text-base font-bold text-theme group-hover:text-orange-500 transition-colors truncate">
                    {selectedFile.name}
                  </p>
                  <p className="text-xs text-theme-muted">{formatFileSize(selectedFile.size)}</p>
                </div>
                <div className="w-10 h-10 shrink-0 rounded-xl bg-orange-500/10 border border-orange-500/20 flex items-center justify-center text-orange-500">
                  <FileText className="w-4 h-4" />
                </div>
              </div>
            ) : (
              <div className="rounded-[1.5rem] border border-[var(--section-border)] bg-[var(--card-bg)] p-5 shadow-sm text-sm text-theme-muted">
                Upload or capture the front of your CNIC to continue. No identity details are extracted yet.
              </div>
            )}
            <div className="rounded-[1.5rem] border border-orange-200/60 bg-orange-50/80 p-5 dark:border-orange-500/20 dark:bg-orange-500/10 flex gap-3">
              <Shield className="w-5 h-5 text-orange-500 mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-extrabold text-orange-700 dark:text-orange-300 text-sm">Pending Verification</p>
                <p className="mt-1 text-xs text-theme-muted leading-relaxed">
                  Your document will be checked against NADRA records after you submit. No name or CNIC number is confirmed at this stage.
                </p>
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
            {isLoading ? "Confirming..." : "Confirm & Continue"}
            <ArrowRight className="h-5 w-5" />
          </Button>
        </motion.aside>
      </div>
    </VerificationPageShell>
  )
}

