"use client"

import { motion, useMotionValue, useSpring, useTransform } from "framer-motion"
import { useEffect, useState, useRef } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"

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
  { id: 8, name: "Canon", logo: "📷", color: "from-red-600 to-red-800" },
  { id: 9, name: "Dell", logo: "💼", color: "from-blue-700 to-blue-900" },
  { id: 10, name: "HP", logo: "🖨️", color: "from-indigo-500 to-indigo-700" },
  { id: 11, name: "Lenovo", logo: "💻", color: "from-red-500 to-orange-600" },
  { id: 12, name: "Xiaomi", logo: "📱", color: "from-orange-400 to-orange-600" }
]

export function BrandCarousel() {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isAutoRotating, setIsAutoRotating] = useState(true)
  const containerRef = useRef<HTMLDivElement>(null)
  
  // Mouse tracking for tilt effect
  const mouseX = useMotionValue(0)
  const mouseY = useMotionValue(0)
  
  const rotateX = useSpring(useTransform(mouseY, [-100, 100], [15, -15]), {
    damping: 25,
    stiffness: 700
  })
  
  const rotateY = useSpring(useTransform(mouseX, [-100, 100], [-15, 15]), {
    damping: 25,
    stiffness: 700
  })

  // Auto-rotation
  useEffect(() => {
    if (!isAutoRotating) return
    
    const interval = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % brands.length)
    }, 3000) // Rotate every 3 seconds

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
    
    for (let i = -2; i <= 2; i++) {
      const index = (currentIndex + i + totalBrands) % totalBrands
      const offset = i
      visible.push({ ...brands[index], offset })
    }
    
    return visible
  }

  const nextBrand = () => {
    setCurrentIndex((prev) => (prev + 1) % brands.length)
    setIsAutoRotating(false)
    setTimeout(() => setIsAutoRotating(true), 5000) // Resume auto-rotation after 5 seconds
  }

  const prevBrand = () => {
    setCurrentIndex((prev) => (prev - 1 + brands.length) % brands.length)
    setIsAutoRotating(false)
    setTimeout(() => setIsAutoRotating(true), 5000) // Resume auto-rotation after 5 seconds
  }

  const visibleBrands = getVisibleBrands()

  return (
    <div className="py-20 bg-gradient-to-br from-gray-50 to-gray-100 relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute inset-0">
        <div className="absolute top-20 left-20 w-64 h-64 bg-orange-200 rounded-full mix-blend-multiply filter blur-xl opacity-30 animate-pulse" />
        <div className="absolute bottom-20 right-20 w-96 h-96 bg-blue-200 rounded-full mix-blend-multiply filter blur-xl opacity-30 animate-pulse animation-delay-2000" />
      </div>

      <div className="container mx-auto px-4 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl lg:text-5xl font-bold text-gray-900 mb-4">
            Trusted by{" "}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-orange-500 to-pink-500">
              Leading Brands
            </span>
          </h2>
          <p className="text-xl text-gray-600 max-w-3xl mx-auto">
            Shop from your favorite brands with instant financing and flexible payment plans
          </p>
        </motion.div>

        {/* Circular Carousel */}
        <div className="relative flex items-center justify-center">
          <div 
            ref={containerRef}
            className="relative w-96 h-96 flex items-center justify-center"
          >
            {/* Center brand */}
            <motion.div
              style={{
                rotateX,
                rotateY,
                transformPerspective: 1000,
              }}
              className="absolute inset-0 flex items-center justify-center"
            >
              <motion.div
                key={visibleBrands[2].id}
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ duration: 0.5 }}
                className="w-32 h-32 bg-gradient-to-br from-white to-gray-50 rounded-3xl shadow-2xl flex items-center justify-center border-2 border-gray-200"
              >
                <div className="text-center">
                  <div className="text-5xl mb-2">{visibleBrands[2].logo}</div>
                  <div className="text-sm font-semibold text-gray-800">{visibleBrands[2].name}</div>
                </div>
              </motion.div>
            </motion.div>

            {/* Fan-like surrounding brands */}
            {visibleBrands.map((brand, index) => {
              if (index === 2) return null // Skip center brand
              
              const angle = (index - 2) * 30 // 30 degrees apart
              const radius = 150
              const x = Math.sin((angle * Math.PI) / 180) * radius
              const y = -Math.cos((angle * Math.PI) / 180) * radius
              const scale = index === 2 ? 1 : 0.6 - Math.abs(index - 2) * 0.1
              const opacity = index === 2 ? 1 : 0.7 - Math.abs(index - 2) * 0.15

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
                    transformPerspective: 1000,
                  }}
                >
                  <div className={`w-24 h-24 bg-gradient-to-br ${brand.color} rounded-2xl shadow-lg flex items-center justify-center border-2 border-white/50`}>
                    <div className="text-center">
                      <div className="text-3xl mb-1">{brand.logo}</div>
                      <div className="text-xs font-semibold text-white">{brand.name}</div>
                    </div>
                  </div>
                </motion.div>
              )
            })}
          </div>

          {/* Navigation buttons */}
          <button
            onClick={prevBrand}
            className="absolute left-4 top-1/2 transform -translate-y-1/2 w-12 h-12 bg-white/80 backdrop-blur-sm rounded-full shadow-lg flex items-center justify-center hover:bg-white transition-colors z-20"
          >
            <ChevronLeft className="w-6 h-6 text-gray-700" />
          </button>
          
          <button
            onClick={nextBrand}
            className="absolute right-4 top-1/2 transform -translate-y-1/2 w-12 h-12 bg-white/80 backdrop-blur-sm rounded-full shadow-lg flex items-center justify-center hover:bg-white transition-colors z-20"
          >
            <ChevronRight className="w-6 h-6 text-gray-700" />
          </button>
        </div>

        {/* Brand indicators */}
        <div className="flex justify-center space-x-2 mt-12">
          {brands.map((_, index) => (
            <button
              key={index}
              onClick={() => {
                setCurrentIndex(index)
                setIsAutoRotating(false)
                setTimeout(() => setIsAutoRotating(true), 5000)
              }}
              className={`w-2 h-2 rounded-full transition-all duration-300 ${
                index === currentIndex 
                  ? 'w-8 bg-gradient-to-r from-orange-500 to-pink-500' 
                  : 'bg-gray-300 hover:bg-gray-400'
              }`}
            />
          ))}
        </div>

        {/* Auto-rotation indicator */}
        <div className="flex justify-center mt-6">
          <div className="flex items-center space-x-2 text-sm text-gray-600">
            <div className={`w-2 h-2 rounded-full ${isAutoRotating ? 'bg-green-500' : 'bg-gray-400'}`} />
            <span>{isAutoRotating ? 'Auto-rotating' : 'Manual mode'}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
