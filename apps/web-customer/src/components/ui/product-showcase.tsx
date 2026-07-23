"use client"

import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { ShoppingCart, Heart, Star, TrendingUp, Package, Zap, Shield, Truck } from "lucide-react"

interface ShowcaseProduct {
  id: number
  name: string
  category: string
  price: string
  discount: string
  rating: number
  image: string
  badge?: string
  features: string[]
}

const showcaseProducts: ShowcaseProduct[] = [
  {
    id: 1,
    name: "iPhone 15 Pro Max",
    category: "Smartphones",
    price: "PKR 319,999",
    discount: "20% OFF",
    rating: 4.8,
    image: "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=400&q=80",
    badge: "Best Seller",
    features: ["A17 Pro", "Titanium", "48MP Camera"]
  },
  {
    id: 2,
    name: "MacBook Pro 16\"",
    category: "Laptops",
    price: "PKR 459,999",
    discount: "15% OFF",
    rating: 4.9,
    image: "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=400&q=80",
    badge: "Premium",
    features: ["M3 Max", "32GB RAM", "1TB SSD"]
  },
  {
    id: 3,
    name: "Sony WH-1000XM5",
    category: "Audio",
    price: "PKR 89,999",
    discount: "25% OFF",
    rating: 4.7,
    image: "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=400&q=80",
    features: ["Noise Cancel", "30hr Battery", "HD Audio"]
  },
  {
    id: 4,
    name: "Samsung Galaxy S24 Ultra",
    category: "Smartphones",
    price: "PKR 289,999",
    discount: "18% OFF",
    rating: 4.6,
    image: "https://images.unsplash.com/photo-1510557880182-3dcf5b0df4b0?auto=format&fit=crop&w=400&q=80",
    badge: "New",
    features: ["S Pen", "200MP Camera", "5G"]
  },
  {
    id: 5,
    name: "iPad Pro 12.9\"",
    category: "Tablets",
    price: "PKR 199,999",
    discount: "12% OFF",
    rating: 4.8,
    image: "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?auto=format&fit=crop&w=400&q=80",
    features: ["M2 Chip", "Liquid Retina", "5G"]
  },
  {
    id: 6,
    name: "Apple Watch Ultra 2",
    category: "Wearables",
    price: "PKR 149,999",
    discount: "10% OFF",
    rating: 4.9,
    image: "https://images.unsplash.com/photo-1523275335684-e0f698d48a1a?auto=format&fit=crop&w=400&q=80",
    badge: "Premium",
    features: ["Titanium", "GPS", "100m Water"]
  },
  {
    id: 7,
    name: "Canon EOS R5",
    category: "Cameras",
    price: "PKR 559,999",
    discount: "22% OFF",
    rating: 4.8,
    image: "https://images.unsplash.com/photo-1502740508437-0ccf6998c905?auto=format&fit=crop&w=400&q=80",
    features: ["45MP", "8K Video", "IBIS"]
  },
  {
    id: 8,
    name: "PlayStation 5",
    category: "Gaming",
    price: "PKR 89,999",
    discount: "30% OFF",
    rating: 4.7,
    image: "https://images.unsplash.com/photo-1492744992467-428c565c5150?auto=format&fit=crop&w=400&q=80",
    badge: "Gaming",
    features: ["4K Gaming", "SSD", "Ray Tracing"]
  }
]

export function ProductShowcase() {
  const [duplicatedProducts, setDuplicatedProducts] = useState<ShowcaseProduct[]>([])

  useEffect(() => {
    // Duplicate products for seamless loop
    setDuplicatedProducts([...showcaseProducts, ...showcaseProducts, ...showcaseProducts])
  }, [])

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case "Smartphones": return <Zap className="w-4 h-4" />
      case "Laptops": return <Package className="w-4 h-4" />
      case "Audio": return <Shield className="w-4 h-4" />
      case "Tablets": return <Truck className="w-4 h-4" />
      case "Wearables": return <Heart className="w-4 h-4" />
      case "Cameras": return <Star className="w-4 h-4" />
      case "Gaming": return <TrendingUp className="w-4 h-4" />
      default: return <Package className="w-4 h-4" />
    }
  }

  return (
    <div className="py-20 bg-gradient-to-br from-gray-900 to-gray-800 relative overflow-hidden">
      {/* Background Effects */}
      <div className="absolute inset-0">
        <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-orange-500/10 to-pink-500/10" />
        <motion.div
          className="absolute top-20 left-20 w-96 h-96 bg-orange-500/20 rounded-full blur-3xl"
          animate={{
            scale: [1, 1.2, 1],
            opacity: [0.3, 0.5, 0.3],
          }}
          transition={{
            duration: 8,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        />
        <motion.div
          className="absolute bottom-20 right-20 w-96 h-96 bg-pink-500/20 rounded-full blur-3xl"
          animate={{
            scale: [1.2, 1, 1.2],
            opacity: [0.5, 0.3, 0.5],
          }}
          transition={{
            duration: 8,
            repeat: Infinity,
            ease: "easeInOut",
            delay: 4
          }}
        />
      </div>

      <div className="container mx-auto px-4 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl lg:text-5xl font-bold text-white mb-4">
            Shop{" "}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-pink-400">
              Everything
            </span>
          </h2>
          <p className="text-xl text-gray-300 max-w-3xl mx-auto">
            From smartphones to gaming consoles, we've got all your favorite products with instant financing
          </p>
        </motion.div>

        {/* Moving Product Showcase */}
        <div className="relative">
          {/* Top Row - Moving Left */}
          <div className="mb-8">
            <motion.div
              className="flex space-x-6"
              animate={{
                x: [0, -showcaseProducts.length * 320]
              }}
              transition={{
                x: {
                  repeat: Infinity,
                  repeatType: "loop",
                  duration: 25,
                  ease: "linear",
                },
              }}
              >
                {duplicatedProducts.map((product, index) => (
                <motion.div
                  key={`top-${product.id}-${index}`}
                  className="flex-shrink-0 w-80 bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 p-6 hover:bg-white/20 transition-all duration-300"
                  whileHover={{ scale: 1.02, y: -5 }}
                  style={{ y: index % 2 === 0 ? 0 : 20 }}
                >
                  <div className="flex items-start space-x-4">
                    <div className="relative w-24 h-24 rounded-3xl overflow-hidden flex-shrink-0">
                      <img
                        src={product.image}
                        alt={product.name}
                        className="w-full h-full object-cover"
                      />
                      <div className="absolute top-2 right-2 bg-white/90 rounded-full p-1 shadow-sm">
                        {getCategoryIcon(product.category)}
                      </div>
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center space-x-2 mb-2">
                        <span className="text-xs font-medium text-orange-400 bg-orange-400/20 px-2 py-1 rounded-full">
                          {product.category}
                        </span>
                        {product.badge && (
                          <span className="text-xs font-medium text-pink-400 bg-pink-400/20 px-2 py-1 rounded-full">
                            {product.badge}
                          </span>
                        )}
                      </div>
                      <h3 className="font-bold text-white text-lg mb-1">{product.name}</h3>
                      <div className="flex items-center space-x-2 mb-2">
                        <span className="text-xl font-bold text-orange-400">{product.price}</span>
                        <span className="text-sm text-green-400 bg-green-400/20 px-2 py-1 rounded-full">
                          {product.discount}
                        </span>
                      </div>
                      <div className="flex items-center space-x-1 mb-3">
                        {[...Array(5)].map((_, i) => (
                          <div
                            key={i}
                            className={`w-3 h-3 rounded-full ${
                              i < Math.floor(product.rating)
                                ? "bg-yellow-400"
                                : "bg-white/30"
                            }`}
                          />
                        ))}
                        <span className="text-xs text-gray-300 ml-1">({product.rating})</span>
                      </div>
                      <div className="flex flex-wrap gap-1 mb-3">
                        {product.features.slice(0, 2).map((feature, idx) => (
                          <span key={idx} className="text-xs text-gray-300 bg-white/10 px-2 py-1 rounded-full">
                            {feature}
                          </span>
                        ))}
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => window.location.href = '/auth/login'}
                          className="flex-1 bg-gradient-to-r from-orange-500 to-pink-500 text-white px-3 py-2 rounded-lg text-sm font-medium hover:from-orange-600 hover:to-pink-600 transition-colors"
                        >
                          Finance Now
                        </button>
                        <button
                          onClick={() => {
                            alert('Added to cart! This feature will be implemented with cart management.')
                          }}
                          className="bg-white/20 text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-white/30 transition-colors"
                        >
                          <ShoppingCart className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          </div>

          {/* Bottom Row - Moving Right */}
          <div>
            <motion.div
              className="flex space-x-6"
              animate={{
                x: [-showcaseProducts.length * 320, 0]
              }}
              transition={{
                x: {
                  repeat: Infinity,
                  repeatType: "loop",
                  duration: 30,
                  ease: "linear",
                },
              }}
            >
              {duplicatedProducts.map((product, index) => (
                <motion.div
                  key={`bottom-${product.id}-${index}`}
                  className="flex-shrink-0 w-80 bg-white/10 backdrop-blur-md rounded-2xl border border-white/20 p-6 hover:bg-white/20 transition-all duration-300"
                  whileHover={{ scale: 1.02, y: -5 }}
                  style={{ y: index % 2 === 0 ? 20 : 0 }}
                >
                  <div className="flex items-start space-x-4">
                    <div className="relative w-24 h-24 rounded-3xl overflow-hidden flex-shrink-0">
                      <img
                        src={product.image}
                        alt={product.name}
                        className="w-full h-full object-cover"
                      />
                      <div className="absolute top-2 right-2 bg-white/90 rounded-full p-1 shadow-sm">
                        <ShoppingCart className="w-6 h-6 text-orange-500" />
                      </div>
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center space-x-2 mb-2">
                        <span className="text-xs font-medium text-pink-400 bg-pink-400/20 px-2 py-1 rounded-full">
                          {product.category}
                        </span>
                        <span className="text-xs font-medium text-green-400 bg-green-400/20 px-2 py-1 rounded-full">
                          In Stock
                        </span>
                      </div>
                      <h3 className="font-bold text-white text-lg mb-1">{product.name}</h3>
                      <div className="flex items-center space-x-2 mb-3">
                        <span className="text-xl font-bold text-pink-400">{product.price}</span>
                        <span className="text-sm text-orange-400 bg-orange-400/20 px-2 py-1 rounded-full">
                          {product.discount}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-1">
                          {[...Array(5)].map((_, i) => (
                            <div
                              key={i}
                              className={`w-3 h-3 rounded-full ${
                                i < Math.floor(product.rating)
                                  ? "bg-yellow-400"
                                  : "bg-white/30"
                              }`}
                            />
                          ))}
                        </div>
                        <button className="px-3 py-1 bg-gradient-to-r from-orange-500 to-pink-500 text-white text-sm font-semibold rounded-lg hover:from-orange-600 hover:to-pink-600 transition-all duration-300">
                          Shop Now
                        </button>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          </div>
        </div>

        {/* Gradient Overlays */}
        <div className="absolute left-0 top-0 bottom-0 w-32 bg-gradient-to-r from-gray-900 via-gray-900/90 to-transparent pointer-events-none z-20" />
        <div className="absolute right-0 top-0 bottom-0 w-32 bg-gradient-to-l from-gray-900 via-gray-900/90 to-transparent pointer-events-none z-20" />
      </div>
    </div>
  )
}
