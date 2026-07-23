"use client"

import { motion, useMotionValue, useSpring, useTransform } from "framer-motion"
import { useEffect, useState, useRef } from "react"

interface Brand {
  id: number
  name: string
  logo: string
  color: string
}

const brands: Brand[] = [
  { id: 1, name: "Apple", logo: "🍎", color: "from-gray-600 to-gray-800" },
  { id: 2, name: "Samsung", logo: "📱", color: "from-blue-500 to-blue-700" },
  { id: 3, name: "Nike", logo: "👟", color: "from-orange-500 to-orange-700" },
  { id: 4, name: "Adidas", logo: "⚽", color: "from-black to-gray-700" },
  { id: 5, name: "Sony", logo: "🎮", color: "from-blue-600 to-purple-600" },
  { id: 6, name: "LG", logo: "📺", color: "from-red-500 to-pink-600" },
  { id: 7, name: "Microsoft", logo: "💻", color: "from-blue-400 to-blue-600" },
  { id: 8, name: "Canon", logo: "📷", color: "from-red-600 to-red-800" }
]

export function HeaderBrandCarousel() {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isAutoRotating, setIsAutoRotating] = useState(true)
  const containerRef = useRef<HTMLDivElement>(null)
  
  // Mouse tracking for tilt effect
  const mouseX = useMotionValue(0)
  const mouseY = useMotionValue(0)
  
  const rotateX = useSpring(useTransform(mouseY, [-50, 50], [10, -10]), {
    damping: 25,
    stiffness: 700
  })
  
  const rotateY = useSpring(useTransform(mouseX, [-50, 50], [-10, 10]), {
    damping: 25,
    stiffness: 700
  })

  // Auto-rotation
  useEffect(() => {
    if (!isAutoRotating) return
    
    const interval = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % brands.length)
    }, 2000) // Rotate every 2 seconds

    return () => clearInterval(interval)
  }, [isAutoRotating])

  // Mouse tracking
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

  const getVisibleBrands = () => {
    const visible = []
    const totalBrands = brands.length
    
    for (let i = -1; i <= 1; i++) {
      const index = (currentIndex + i + totalBrands) % totalBrands
      const offset = i
      visible.push({ ...brands[index], offset })
    }
    
    return visible
  }

  const visibleBrands = getVisibleBrands()

  return (
    <div 
      ref={containerRef}
      className="relative w-48 h-48 flex items-center justify-center"
    >
      {/* Background decoration */}
      <div className="absolute inset-0 bg-gradient-to-br from-orange-100/20 to-pink-100/20 rounded-full blur-xl" />
      
      {/* Fan-like surrounding brands */}
      {visibleBrands.map((brand, index) => {
        const angle = index * 40 // 40 degrees apart
        const radius = 60
        const x = Math.sin((angle * Math.PI) / 180) * radius
        const y = -Math.cos((angle * Math.PI) / 180) * radius
        const scale = index === 1 ? 1 : 0.7 - Math.abs(index - 1) * 0.2
        const opacity = index === 1 ? 1 : 0.6 - Math.abs(index - 1) * 0.2

        return (
          <motion.div
            key={`${brand.id}-${index}`}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ 
              scale, 
              opacity,
              x,
              y,
              rotateZ: -angle
            }}
            transition={{ 
              duration: 0.6,
              ease: "easeInOut"
            }}
            className="absolute"
            style={{
              transformPerspective: 800,
            }}
          >
            <motion.div
              style={{
                rotateX,
                rotateY,
                transformPerspective: 800,
              }}
              className={`w-16 h-16 bg-gradient-to-br ${brand.color} rounded-xl shadow-lg flex items-center justify-center border-2 border-white/50`}
            >
              <div className="text-center">
                <div className="text-2xl">{brand.logo}</div>
              </div>
            </motion.div>
          </motion.div>
        )
      })}

      {/* Center brand name */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
        className="absolute bottom-0 text-center"
      >
        <div className="text-xs font-semibold text-gray-700 bg-white/80 backdrop-blur-sm px-2 py-1 rounded-full">
          {visibleBrands[1].name}
        </div>
      </motion.div>
    </div>
  )
}
