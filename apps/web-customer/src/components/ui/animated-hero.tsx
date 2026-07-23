"use client"

import { motion, useMotionValue, useSpring } from "framer-motion"
import { useEffect, useState, useRef } from "react"
import { ShoppingCart, Smartphone, Laptop, Watch, Camera, Headphones } from "lucide-react"

interface HeroImage {
  id: number
  text: string
  icon: React.ReactNode
  color: string
  delay: number
}

const heroImages: HeroImage[] = [
  { id: 1, text: "S", icon: <ShoppingCart className="w-8 h-8" />, color: "from-orange-400 to-orange-600", delay: 0 },
  { id: 2, text: "A", icon: <Smartphone className="w-8 h-8" />, color: "from-blue-400 to-blue-600", delay: 0.2 },
  { id: 3, text: "H", icon: <Laptop className="w-8 h-8" />, color: "from-purple-400 to-purple-600", delay: 0.4 },
  { id: 4, text: "U", icon: <Watch className="w-8 h-8" />, color: "from-green-400 to-green-600", delay: 0.6 },
  { id: 5, text: "L", icon: <Camera className="w-8 h-8" />, color: "from-red-400 to-red-600", delay: 0.8 },
  { id: 6, text: "A", icon: <Headphones className="w-8 h-8" />, color: "from-yellow-400 to-yellow-600", delay: 1.0 },
  { id: 7, text: "T", icon: <ShoppingCart className="w-8 h-8" />, color: "from-pink-400 to-pink-600", delay: 1.2 },
  { id: 8, text: "K", icon: <Smartphone className="w-8 h-8" />, color: "from-indigo-400 to-indigo-600", delay: 1.4 },
  { id: 9, text: "A", icon: <Laptop className="w-8 h-8" />, color: "from-teal-400 to-teal-600", delay: 1.6 },
  { id: 10, text: "R", icon: <Watch className="w-8 h-8" />, color: "from-cyan-400 to-cyan-600", delay: 1.8 }
]

export function AnimatedHero() {
  const [isClient, setIsClient] = useState(false)
  const [hoveredImage, setHoveredImage] = useState<number | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  
  // Mouse tracking for hover effects
  const mouseX = useMotionValue(0)
  const mouseY = useMotionValue(0)
  
  const translateX = useSpring(mouseX, { damping: 25, stiffness: 700 })
  const translateY = useSpring(mouseY, { damping: 25, stiffness: 700 })

  useEffect(() => {
    setIsClient(true)
  }, [])

  // Mouse tracking for hover effects
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect()
        const centerX = rect.left + rect.width / 2
        const centerY = rect.top + rect.height / 2
        mouseX.set(e.clientX - centerX)
        mouseY.set(e.clientY - centerY)
      }
    }

    const handleMouseLeave = () => {
      mouseX.set(0)
      mouseY.set(0)
    }

    const container = containerRef.current
    if (container) {
      container.addEventListener('mousemove', handleMouseMove)
      container.addEventListener('mouseleave', handleMouseLeave)
    }

    return () => {
      if (container) {
        container.removeEventListener('mousemove', handleMouseMove)
        container.removeEventListener('mouseleave', handleMouseLeave)
      }
    }
  }, [mouseX, mouseY])

  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden bg-gradient-to-br from-gray-900 via-blue-900 to-purple-900">
      {/* Background animated elements */}
      <div className="absolute inset-0">
        <motion.div
          className="absolute top-20 left-20 w-64 h-64 bg-gradient-to-br from-orange-400/30 to-pink-400/30 rounded-full blur-3xl"
          animate={{
            scale: [1, 1.5, 1],
            opacity: [0.3, 0.6, 0.3],
            x: [0, 50, 0],
            y: [0, 30, 0],
          }}
          transition={{
            duration: 8,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        />
        <motion.div
          className="absolute bottom-20 right-20 w-96 h-96 bg-gradient-to-br from-blue-400/30 to-purple-400/30 rounded-full blur-3xl"
          animate={{
            scale: [1.5, 1, 1.5],
            opacity: [0.6, 0.3, 0.6],
            x: [0, -50, 0],
            y: [0, -30, 0],
          }}
          transition={{
            duration: 8,
            repeat: Infinity,
            ease: "easeInOut",
            delay: 4
          }}
        />
      </div>

      {/* Animated Images Container */}
      <div 
        ref={containerRef}
        className="relative z-10 w-full max-w-6xl mx-auto px-4"
      >
        <div className="grid grid-cols-2 md:grid-cols-5 gap-8 mb-16">
          {heroImages.map((image, index) => (
            <motion.div
              key={image.id}
              initial={{ 
                y: 1000, // Start from bottom
                opacity: 0,
                scale: 0
              }}
              animate={{ 
                y: 0, // Move to final position
                opacity: 1,
                scale: 1
              }}
              transition={{ 
                duration: 1.5,
                ease: "easeOut",
                delay: image.delay
              }}
              className="relative"
              onMouseEnter={() => setHoveredImage(image.id)}
              onMouseLeave={() => setHoveredImage(null)}
            >
              <motion.div
                whileHover={{ 
                  x: hoveredImage === image.id ? 20 : 0,
                  rotate: hoveredImage === image.id ? 5 : 0
                }}
                className={`w-32 h-32 md:w-40 md:h-40 bg-gradient-to-br ${image.color} rounded-3xl shadow-2xl flex items-center justify-center border-4 border-white/20 relative overflow-hidden cursor-pointer`}
              >
                {/* Icon */}
                <div className="text-white relative z-10">
                  {image.icon}
                </div>
                
                {/* Glow effect */}
                <motion.div
                  className={`absolute inset-0 bg-gradient-to-br ${image.color} opacity-50 blur-xl`}
                  animate={{ scale: [1, 1.2, 1] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
                
                {/* Dancing Text */}
                <motion.div
                  className="absolute inset-0 flex items-center justify-center"
                  initial={{ scale: 0, rotate: -180 }}
                  animate={{ 
                    scale: 1, 
                    rotate: 0,
                    y: [0, -10, 0]
                  }}
                  transition={{ 
                    duration: 0.8,
                    delay: image.delay + 0.5,
                    y: { repeat: Infinity, duration: 2 }
                  }}
                >
                  <span className="text-white font-black text-2xl md:text-3xl drop-shadow-lg">
                    {image.text}
                  </span>
                </motion.div>

                {/* Hover effect overlay */}
                {hoveredImage === image.id && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="absolute inset-0 bg-white/20 rounded-3xl"
                  />
                )}
              </motion.div>
            </motion.div>
          ))}
        </div>

        {/* Main Title */}
        <motion.div
          initial={{ opacity: 0, y: 50 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, delay: 2 }}
          className="text-center"
        >
          <h1 className="text-4xl md:text-6xl lg:text-8xl font-black text-white mb-6 leading-tight">
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-orange-400 via-pink-400 to-purple-400">
              SAHULATKAR
            </span>
          </h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 2.5 }}
            className="text-xl md:text-2xl text-white/80 max-w-3xl mx-auto mb-8"
          >
            Your Premium Financial Partner for Instant Shopping
          </motion.p>
          
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, delay: 3 }}
            className="flex flex-col sm:flex-row gap-4 justify-center"
          >
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="px-8 py-4 bg-gradient-to-r from-orange-500 to-pink-500 text-white font-bold rounded-full shadow-lg hover:shadow-xl transition-shadow"
            >
              Get Started Now
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="px-8 py-4 bg-white/20 backdrop-blur-sm text-white font-bold rounded-full border-2 border-white/30 hover:bg-white/30 transition-colors"
            >
              Learn More
            </motion.button>
          </motion.div>
        </motion.div>
      </div>

      {/* Floating particles */}
      {isClient && [...Array(20)].map((_, i) => (
        <motion.div
          key={i}
          className="absolute w-2 h-2 bg-white/40 rounded-full"
          initial={{
            x: (i * 100 - 500) % window.innerWidth,
            y: window.innerHeight + 100,
          }}
          animate={{
            y: -100,
            opacity: [0, 1, 0],
            scale: [0, 1, 0],
          }}
          transition={{
            duration: 5 + (i * 0.5),
            repeat: Infinity,
            delay: i * 0.3,
            ease: "easeOut"
          }}
        />
      ))}
    </section>
  )
}
