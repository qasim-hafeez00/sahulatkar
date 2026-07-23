"use client"

import { motion, AnimatePresence } from "framer-motion"
import { useEffect, useState } from "react"

const LOGO_SHIMMER_CSS = `
@keyframes shimmer-move {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

@keyframes orbit-cw {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@keyframes orbit-ccw {
  0% { transform: rotate(360deg); }
  100% { transform: rotate(0deg); }
}

@keyframes pulse-ring {
  0%, 100% { transform: scale(0.97); opacity: 0.85; }
  50% { transform: scale(1.03); opacity: 1; }
}

@keyframes blob-float-1 {
  0%, 100% { transform: translate(0px, 0px) scale(1); }
  33% { transform: translate(60px, -80px) scale(1.2); }
  66% { transform: translate(-40px, 60px) scale(0.85); }
}

@keyframes blob-float-2 {
  0%, 100% { transform: translate(0px, 0px) scale(1); }
  40% { transform: translate(-70px, 70px) scale(1.25); }
  75% { transform: translate(70px, -40px) scale(0.8); }
}

@keyframes blob-float-3 {
  0%, 100% { transform: translate(0px, 0px) scale(1); }
  50% { transform: translate(80px, 40px) scale(1.15); }
  80% { transform: translate(-50px, -50px) scale(0.9); }
}

@keyframes float-particle {
  0% { transform: translateY(110vh) translateX(0) scale(1); opacity: 0; }
  15% { opacity: 0.7; }
  85% { opacity: 0.5; }
  100% { transform: translateY(-10vh) translateX(60px) scale(0.4); opacity: 0; }
}

.gold-metallic-text {
  background: linear-gradient(
    135deg, 
    #ffffff 0%, 
    #fff7ed 20%, 
    #fed7aa 40%, 
    #f97316 50%, 
    #fed7aa 60%, 
    #ffffff 80%, 
    #fff7ed 100%
  );
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  text-fill-color: transparent;
  animation: shimmer-move 5s linear infinite;
}

.glowing-orb {
  filter: blur(140px);
  mix-blend-mode: plus-lighter;
  will-change: transform;
}
`

export function SplashScreen() {
  const [showSplash, setShowSplash] = useState(true)
  const [showText, setShowText] = useState(false)
  const [statusIndex, setStatusIndex] = useState(0)
  const [progress, setProgress] = useState(0)

  const statusMessages = [
    "SAHULATKAR SECURE VAULT DEPLOYING...",
    "VERIFYING SECP REGULATORY BENCHMARKS...",
    "SHARIAH MURABAHA INTEGRITY CHECKS ACTIVE...",
    "SYNCHRONIZING SECURE DEFI WALLET COUPLING...",
    "SAHULATKAR PREMIUM INTERFACE INITIALIZED."
  ]

  useEffect(() => {
    const header = document.querySelector("header")
    if (header) header.style.visibility = "hidden"

    const textTimer = setTimeout(() => setShowText(true), 200)

    // Smooth progress bar update to complete exactly around 3000ms
    const progressInterval = setInterval(() => {
      setProgress(prev => {
        if (prev >= 100) return 100
        return prev + 1.15
      })
    }, 30)

    // Smooth status text transitions
    const statusInterval = setInterval(() => {
      setStatusIndex(prev => {
        if (prev < statusMessages.length - 1) return prev + 1
        return prev
      })
    }, 600)

    const splashTimer = setTimeout(() => {
      setShowSplash(false)
      if (header) header.style.visibility = ""
    }, 3200)

    return () => {
      clearTimeout(textTimer)
      clearInterval(progressInterval)
      clearInterval(statusInterval)
      clearTimeout(splashTimer)
      if (header) header.style.visibility = ""
    }
  }, [])

  // Static list of particles to remain deterministic
  const particles = [
    { id: 1, left: "8%", size: 6, delay: "0s", duration: "10s" },
    { id: 2, left: "20%", size: 4, delay: "2.5s", duration: "13s" },
    { id: 3, left: "34%", size: 8, delay: "1.2s", duration: "11s" },
    { id: 4, left: "46%", size: 5, delay: "3.8s", duration: "12s" },
    { id: 5, left: "60%", size: 7, delay: "0.5s", duration: "9s" },
    { id: 6, left: "72%", size: 4, delay: "4.2s", duration: "14s" },
    { id: 7, left: "86%", size: 9, delay: "1.8s", duration: "10s" },
    { id: 8, left: "14%", size: 5, delay: "5.1s", duration: "12s" },
    { id: 9, left: "54%", size: 6, delay: "2.1s", duration: "11s" },
    { id: 10, left: "78%", size: 4, delay: "6.0s", duration: "13s" }
  ]

  const brandLetters = "Sahulatkar".split("")

  return (
    <AnimatePresence>
      {showSplash && (
        <motion.div
          initial={{ opacity: 1 }}
          exit={{ 
            opacity: 0, 
            scale: 1.05,
            filter: "blur(12px)",
            transition: { duration: 0.95, ease: [0.22, 1, 0.36, 1] } 
          }}
          className="fixed inset-0 z-[9999] flex flex-col items-center justify-center overflow-hidden bg-[#0a0808]"
        >
          <style dangerouslySetInnerHTML={{ __html: LOGO_SHIMMER_CSS }} />

          {/* Ambient Glowing Orbs Background */}
          <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-90 z-0">
            {/* Deep Purple Blob */}
            <div 
              className="absolute glowing-orb w-[650px] h-[650px] rounded-full bg-[#4c1d95]/35 -left-[10%] -top-[10%]"
              style={{ animation: "blob-float-1 25s infinite ease-in-out" }}
            />
            {/* Vivid Shariah Orange/Amber Blob */}
            <div 
              className="absolute glowing-orb w-[600px] h-[600px] rounded-full bg-[#f97316]/25 -right-[5%] -bottom-[5%]"
              style={{ animation: "blob-float-2 22s infinite ease-in-out" }}
            />
            {/* Rich Pink/Magenta Accent Blob */}
            <div 
              className="absolute glowing-orb w-[550px] h-[550px] rounded-full bg-[#ec4899]/18 left-[20%] top-[25%]"
              style={{ animation: "blob-float-3 28s infinite ease-in-out" }}
            />
            {/* Dark Vignette Layer */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_30%,rgba(10,8,8,0.9)_100%)]" />
          </div>

          {/* Drifting Floating Micro-particles */}
          <div className="absolute inset-0 pointer-events-none z-0">
            {particles.map(p => (
              <div
                key={p.id}
                className="absolute rounded-full bg-orange-400/15"
                style={{
                  left: p.left,
                  width: `${p.size}px`,
                  height: `${p.size}px`,
                  animation: `float-particle ${p.duration} infinite linear`,
                  animationDelay: p.delay,
                  bottom: "-20px"
                }}
              />
            ))}
          </div>

          {/* Central Premium Container */}
          <div className="relative z-10 flex flex-col items-center justify-center max-w-2xl px-6 text-center">
            
            {/* Premium Golden Shariah Logo/Emblem */}
            <motion.div
              initial={{ scale: 0.8, opacity: 0, rotate: -10 }}
              animate={{ scale: 1, opacity: 1, rotate: 0 }}
              transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
              className="relative w-44 h-44 mb-6 flex items-center justify-center"
              style={{ animation: "pulse-ring 6s infinite ease-in-out" }}
            >
              {/* Outer Orbit Tech Dash Ring */}
              <div 
                className="absolute inset-0 rounded-full border border-dashed border-orange-500/25"
                style={{ animation: "orbit-cw 22s infinite linear" }}
              />
              {/* Inner Orbit Tech Dot Ring */}
              <div 
                className="absolute inset-3 rounded-full border border-dotted border-white/15"
                style={{ animation: "orbit-ccw 16s infinite linear" }}
              />

              {/* Radiant Glow Behind */}
              <div className="absolute w-28 h-28 rounded-full bg-gradient-to-r from-orange-600/50 to-amber-500/40 blur-2xl opacity-60 z-0" />

              {/* Shariah-Fintech Luxury Emblem SVG */}
              <svg 
                className="relative z-10 w-28 h-28 drop-shadow-[0_0_30px_rgba(249,115,22,0.6)]" 
                viewBox="0 0 100 100" 
                fill="none" 
                xmlns="http://www.w3.org/2000/svg"
              >
                {/* Crescent Crescent Path */}
                <path
                  d="M32 20C32 20 48 24 48 50C48 76 32 80 32 80C42 80 62 70 62 50C62 30 42 20 32 20Z"
                  fill="url(#crescentGrad)"
                />
                
                {/* Modern Ascent FinTech Diagonal Bars */}
                <path 
                  d="M50 68L64 54M58 76L78 56M66 84L82 68" 
                  stroke="url(#wireframeGrad)" 
                  strokeWidth="2.5" 
                  strokeLinecap="round"
                  opacity="0.8"
                />

                {/* Shariah Compliance Premium Centerpiece Star / Diamond Sparkle */}
                <polygon
                  points="50,14 54,26 66,30 54,34 50,46 46,34 34,30 46,26"
                  fill="url(#goldMetallic)"
                />

                {/* Micro tech node pins */}
                <circle cx="50" cy="30" r="1.5" fill="#FFF" />
                <circle cx="62" cy="50" r="1.5" fill="#f97316" />

                {/* Gradients definitions */}
                <defs>
                  <linearGradient id="crescentGrad" x1="32" y1="20" x2="62" y2="80" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stopColor="#fff7ed" />
                    <stop offset="50%" stopColor="#f97316" />
                    <stop offset="100%" stopColor="#ea580c" />
                  </linearGradient>
                  
                  <linearGradient id="wireframeGrad" x1="50" y1="84" x2="82" y2="54" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stopColor="#d97706" />
                    <stop offset="50%" stopColor="#fb923c" />
                    <stop offset="100%" stopColor="#ffffff" stopOpacity="0.7" />
                  </linearGradient>

                  <linearGradient id="goldMetallic" x1="34" y1="14" x2="66" y2="46" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stopColor="#ffffff" />
                    <stop offset="30%" stopColor="#fde047" />
                    <stop offset="70%" stopColor="#ca8a04" />
                    <stop offset="100%" stopColor="#fef08a" />
                  </linearGradient>
                </defs>
              </svg>
            </motion.div>

            {/* Glowing Brand Name Reveal with letter stagger */}
            {showText && (
              <div 
                className="flex items-center justify-center tracking-[0.02em] overflow-visible mb-5 select-none"
                style={{
                  fontFamily: '"Outfit", "Inter", system-ui, -apple-system, sans-serif'
                }}
              >
                {brandLetters.map((char, index) => (
                  <motion.span
                    key={index}
                    initial={{ opacity: 0, y: 30, scale: 0.75, filter: "blur(5px)" }}
                    animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
                    transition={{
                      duration: 0.75,
                      delay: index * 0.04,
                      ease: [0.22, 1, 0.36, 1]
                    }}
                    className="gold-metallic-text text-[clamp(2.5rem,8vw,5.5rem)] font-black leading-none inline-block drop-shadow-[0_10px_35px_rgba(249,115,22,0.25)]"
                  >
                    {char}
                  </motion.span>
                ))}
              </div>
            )}

            {/* SECP Registered Shariah Fintech Tagline */}
            <motion.p
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 0.85, y: 0 }}
              transition={{ delay: 0.75, duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
              className="text-xs md:text-sm font-semibold tracking-[0.38em] uppercase text-orange-200/50 leading-relaxed max-w-md mx-auto mb-16 select-none"
              style={{ fontFamily: '"Inter", sans-serif' }}
            >
              Shariah Compliant · SECP Registered
            </motion.p>
          </div>

          {/* Secure Live Boot Console and Loader */}
          <div className="absolute bottom-12 left-0 right-0 w-full max-w-sm px-6 mx-auto z-10 flex flex-col items-center">
            
            {/* Live Changing Status Console */}
            <div className="flex items-center gap-2 mb-3.5 text-[9px] md:text-[11px] font-mono tracking-widest text-orange-400/75 uppercase select-none min-h-[16px] text-center">
              <svg 
                className="w-3.5 h-3.5 animate-spin text-orange-400" 
                fill="none" 
                viewBox="0 0 24 24"
              >
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span>{statusMessages[statusIndex]}</span>
            </div>

            {/* Glowing Luxury Thin Progress Bar */}
            <div className="w-full h-[3px] bg-white/5 rounded-full overflow-hidden relative border border-white/5">
              <motion.div 
                className="h-full bg-gradient-to-r from-orange-600 via-orange-400 to-amber-300 rounded-full shadow-[0_0_12px_rgba(249,115,22,0.8)]"
                style={{ width: `${progress}%` }}
              />
            </div>

            {/* Boot metadata */}
            <div className="flex justify-between w-full mt-2.5 text-[7.5px] font-mono tracking-widest text-white/25 uppercase select-none">
              <span>SECURE DEFI PROT: SHIELD-AES-256</span>
              <span>VER: 4.8.2-ELITE</span>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

