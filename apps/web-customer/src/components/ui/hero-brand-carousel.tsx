"use client"

import { motion, useMotionValue, useSpring, useTransform, AnimatePresence } from "framer-motion"
import { useEffect, useState, useRef } from "react"
import { Laptop, Smartphone, Watch, Headphones, Camera, Gamepad2, Tablet, ShoppingBag } from "lucide-react"

interface Product {
  id: number
  name: string
  icon: React.ReactNode
  color: string
  position: { x: number; y: number }
  delay: number
}

const products: Product[] = [
  { id: 1, name: "iPhone 15 Pro", icon: <Smartphone className="w-6 h-6" />, color: "from-gray-800 to-gray-900", position: { x: -120, y: -80 }, delay: 0.1 },
  { id: 2, name: "MacBook Pro", icon: <Laptop className="w-8 h-8" />, color: "from-gray-700 to-gray-900", position: { x: 0, y: -100 }, delay: 0.2 },
  { id: 3, name: "Apple Watch", icon: <Watch className="w-5 h-5" />, color: "from-gray-600 to-gray-800", position: { x: 120, y: -80 }, delay: 0.3 },
  { id: 4, name: "AirPods Pro", icon: <Headphones className="w-6 h-6" />, color: "from-white to-gray-200", position: { x: -140, y: 20 }, delay: 0.4 },
  { id: 5, name: "Canon EOS", icon: <Camera className="w-6 h-6" />, color: "from-red-600 to-red-800", position: { x: 140, y: 20 }, delay: 0.5 },
  { id: 6, name: "PlayStation 5", icon: <Gamepad2 className="w-6 h-6" />, color: "from-blue-600 to-blue-800", position: { x: -100, y: 100 }, delay: 0.6 },
  { id: 7, name: "iPad Pro", icon: <Tablet className="w-6 h-6" />, color: "from-gray-500 to-gray-700", position: { x: 100, y: 100 }, delay: 0.7 },
  { id: 8, name: "Shopping Bag", icon: <ShoppingBag className="w-6 h-6" />, color: "from-orange-500 to-orange-600", position: { x: 0, y: 120 }, delay: 0.8 }
]

export function HeroBrandCarousel() {
  const [visibleProducts, setVisibleProducts] = useState<Product[]>([])
  const [hoveredProduct, setHoveredProduct] = useState<number | null>(null)
  const [isClient, setIsClient] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Fix hydration by setting isClient only after mount
  useEffect(() => {
    setIsClient(true)
  }, [])
  
  // Mouse tracking for tilt effect
  const mouseX = useMotionValue(0)
  const mouseY = useMotionValue(0)
  
  const rotateX = useSpring(useTransform(mouseY, [-150, 150], [10, -10]), {
    damping: 25,
    stiffness: 700
  })
  
  const rotateY = useSpring(useTransform(mouseX, [-150, 150], [-10, 10]), {
    damping: 25,
    stiffness: 700
  })

  // Auto-rotation of products
  useEffect(() => {
    const interval = setInterval(() => {
      setVisibleProducts(prev => {
        if (prev.length === 0) {
          return products.slice(0, 5) // Start with 5 products
        }
        
        // Rotate products: remove first, add new one
        const newProducts = [...prev.slice(1)]
        const nextIndex = (prev[prev.length - 1].id % products.length) + 1
        const newProduct = products.find(p => p.id === nextIndex)
        
        if (newProduct && !newProducts.find(p => p.id === newProduct.id)) {
          newProducts.push(newProduct)
        }
        
        return newProducts
      })
    }, 2000) // Rotate every 2 seconds

    return () => clearInterval(interval)
  }, [])

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

  return (
    <div 
      ref={containerRef}
      className="relative w-96 h-96 flex items-center justify-center"
    >
      {/* Magical background effects */}
      <div className="absolute inset-0">
        <motion.div
          className="absolute inset-0 bg-gradient-to-br from-orange-400/20 via-pink-400/20 to-purple-400/20 rounded-full blur-3xl"
          animate={{
            scale: [1, 1.2, 1],
            rotate: [0, 180, 360],
          }}
          transition={{
            duration: 8,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        />
        <motion.div
          className="absolute top-1/4 left-1/4 w-32 h-32 bg-gradient-to-br from-yellow-400/30 to-orange-400/30 rounded-full blur-2xl"
          animate={{
            scale: [1, 1.5, 1],
            opacity: [0.3, 0.6, 0.3],
          }}
          transition={{
            duration: 4,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        />
        <motion.div
          className="absolute bottom-1/4 right-1/4 w-32 h-32 bg-gradient-to-br from-blue-400/30 to-purple-400/30 rounded-full blur-2xl"
          animate={{
            scale: [1.5, 1, 1.5],
            opacity: [0.6, 0.3, 0.6],
          }}
          transition={{
            duration: 4,
            repeat: Infinity,
            ease: "easeInOut",
            delay: 2
          }}
        />
      </div>

      {/* Center Laptop */}
      <motion.div
        style={{
          rotateX,
          rotateY,
          transformPerspective: 1200,
        }}
        className="relative z-20"
      >
        <motion.div
          initial={{ scale: 0, rotate: -180 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ duration: 1, ease: "easeOut" }}
          className="relative"
        >
          {/* Laptop Screen */}
          <div className="w-48 h-32 bg-gradient-to-br from-gray-900 to-gray-800 rounded-t-2xl border-4 border-gray-700 shadow-2xl relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-blue-600/20 to-purple-600/20" />
            <div className="absolute inset-2 bg-gray-900 rounded-lg flex items-center justify-center">
              <motion.div
                animate={{ opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 2, repeat: Infinity }}
                className="text-orange-400 font-bold text-lg"
              >
                SAHULATKAR
              </motion.div>
            </div>
            {/* Screen glow */}
            <div className="absolute inset-0 bg-gradient-to-t from-transparent to-orange-400/10 pointer-events-none" />
          </div>
          
          {/* Laptop Base */}
          <div className="w-56 h-4 bg-gradient-to-br from-gray-700 to-gray-800 rounded-b-lg shadow-xl" />
          
          {/* Laptop Glow */}
          <motion.div
            animate={{ opacity: [0.3, 0.8, 0.3] }}
            transition={{ duration: 3, repeat: Infinity }}
            className="absolute inset-0 bg-gradient-to-br from-orange-400/20 to-pink-400/20 rounded-2xl blur-xl pointer-events-none"
          />
        </motion.div>
      </motion.div>

      {/* Popping Products */}
      <AnimatePresence>
        {visibleProducts.map((product) => (
          <motion.div
            key={product.id}
            initial={{ 
              scale: 0, 
              opacity: 0,
              x: 0,
              y: 0
            }}
            animate={{ 
              scale: hoveredProduct === product.id ? 1.2 : 1,
              opacity: 1,
              x: product.position.x,
              y: product.position.y,
              rotate: hoveredProduct === product.id ? 5 : 0
            }}
            exit={{ 
              scale: 0, 
              opacity: 0,
              x: 50,
              y: -50
            }}
            transition={{ 
              duration: 0.6,
              ease: "easeOut",
              delay: product.delay
            }}
            className="absolute z-10"
            onMouseEnter={() => setHoveredProduct(product.id)}
            onMouseLeave={() => setHoveredProduct(null)}
          >
            <motion.div
              whileHover={{ scale: 1.1, rotate: 5 }}
              className={`w-16 h-16 bg-gradient-to-br ${product.color} rounded-2xl shadow-2xl flex items-center justify-center border-2 border-white/30 relative overflow-hidden`}
            >
              {/* Product icon */}
              <div className="text-white relative z-10">
                {product.icon}
              </div>
              
              {/* Glow effect */}
              <motion.div
                className={`absolute inset-0 bg-gradient-to-br ${product.color} opacity-50 blur-md`}
                animate={{ scale: [1, 1.2, 1] }}
                transition={{ duration: 2, repeat: Infinity }}
              />
              
              {/* Hover tooltip */}
              {hoveredProduct === product.id && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="absolute -top-10 left-1/2 transform -translate-x-1/2 bg-gray-900 text-white text-xs px-3 py-1 rounded-full whitespace-nowrap z-30"
                >
                  {product.name}
                </motion.div>
              )}
            </motion.div>
          </motion.div>
        ))}
      </AnimatePresence>

      {/* Floating particles */}
      {isClient && [...Array(6)].map((_, i) => (
        <motion.div
          key={i}
          className="absolute w-2 h-2 bg-orange-400/60 rounded-full"
          initial={{
            x: (i * 60 - 150) % 200 - 100,
            y: (i * 45 - 100) % 200 - 100,
          }}
          animate={{
            y: [0, -20, 0],
            opacity: [0.3, 0.8, 0.3],
            scale: [1, 1.5, 1],
          }}
          transition={{
            duration: 3 + (i * 0.5),
            repeat: Infinity,
            delay: i * 0.3,
            ease: "easeInOut"
          }}
        />
      ))}

      {/* Bottom label */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, delay: 1 }}
        className="absolute bottom-0 text-center"
      >
        <div className="text-sm font-bold text-gray-800 bg-white/90 backdrop-blur-sm px-4 py-2 rounded-full shadow-lg border border-orange-200">
          <span className="text-orange-600">✨</span> Premium Products <span className="text-orange-600">✨</span>
        </div>
      </motion.div>
    </div>
  )
}
