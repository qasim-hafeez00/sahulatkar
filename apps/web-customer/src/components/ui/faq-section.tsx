"use client"

import { motion, AnimatePresence } from "framer-motion"
import { useState } from "react"
import { ChevronDown, ChevronUp, HelpCircle, MessageCircle, Shield, CreditCard, ShoppingBag, Truck, RefreshCw, Headphones } from "lucide-react"

interface FAQItem {
  id: number
  question: string
  answer: string
  category: string
  icon: React.ReactNode
  image: string
}

const faqData: FAQItem[] = [
  {
    id: 1,
    question: "How does SahulatKar financing work?",
    answer: "SahulatKar uses Shariah-compliant Murabaha financing. We purchase the product on your behalf and sell it to you at a cost-plus-profit price with flexible installment plans. Simply paste any product URL, get instant approval, and pay in easy monthly installments.",
    category: "Financing",
    icon: <CreditCard className="w-5 h-5" />,
    image: "https://images.unsplash.com/photo-1556742049-0cfed4f6a5d8?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=200&q=80"
  },
  {
    id: 2,
    question: "What products can I finance through SahulatKar?",
    answer: "You can finance almost any product from major e-commerce platforms including Daraz, Amazon, Naheed, Foodpanda, and more. From smartphones and laptops to home appliances and fashion items - if it has a URL, we can finance it!",
    category: "Products",
    icon: <ShoppingBag className="w-5 h-5" />,
    image: "https://images.unsplash.com/photo-1556742049-0cfed4f6a5d8?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=200&q=80"
  },
  {
    id: 3,
    question: "Is the financing really halal and Shariah-compliant?",
    answer: "Yes! Our financing model is 100% Shariah-compliant. We follow the Agency Murabaha structure where we act as your agent to purchase products, then resell them to you at transparent, fixed profit rates with no compounding interest (Riba). All agreements are reviewed by Islamic finance scholars.",
    category: "Shariah",
    icon: <Shield className="w-5 h-5" />,
    image: "https://images.unsplash.com/photo-1554224155-6af6b86a6295?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=200&q=80"
  },
  {
    id: 4,
    question: "How quickly can I get approved for financing?",
    answer: "Our AI-powered credit scoring system provides instant decisions! Most applications are approved within 60 seconds. The system evaluates your profile using advanced algorithms while ensuring responsible lending practices.",
    category: "Process",
    icon: <RefreshCw className="w-5 h-5" />,
    image: "https://images.unsplash.com/photo-1563013544-824ae1b704d3?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=200&q=80"
  },
  {
    id: 5,
    question: "What are the eligibility requirements?",
    answer: "You must be 18+ years old, have a valid CNIC, and a stable source of income. We use advanced credit scoring that considers multiple factors beyond traditional credit history. Higher education and stable employment increase your chances of approval.",
    category: "Requirements",
    icon: <HelpCircle className="w-5 h-5" />,
    image: "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=200&q=80"
  },
  {
    id: 6,
    question: "How long does delivery take after approval?",
    answer: "Delivery times vary by merchant but typically range from 2-7 business days. We work with trusted merchants like Daraz (2-3 days), Amazon (4-6 days), and Naheed (3-5 days). You'll receive real-time tracking updates throughout the delivery process.",
    category: "Delivery",
    icon: <Truck className="w-5 h-5" />,
    image: "https://images.unsplash.com/photo-1563013544-824ae1b704d3?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=200&q=80"
  },
  {
    id: 7,
    question: "Can I pay off my financing early?",
    answer: "Absolutely! You can make early repayments anytime without any penalties or additional charges. In fact, early repayment may even reduce your total profit amount. We encourage responsible financial management.",
    category: "Payments",
    icon: <CreditCard className="w-5 h-5" />,
    image: "https://images.unsplash.com/photo-1554224155-6af6b86a6295?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=200&q=80"
  },
  {
    id: 8,
    question: "What if I miss a payment?",
    answer: "We understand that life happens. If you miss a payment, we'll send reminders through SMS and in-app notifications. While late payments may affect your credit score, we work with you to find solutions. Multiple missed payments may require account review.",
    category: "Payments",
    icon: <MessageCircle className="w-5 h-5" />,
    image: "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=200&q=80"
  },
  {
    id: 9,
    question: "How do I contact customer support?",
    answer: "Our support team is available 24/7 through multiple channels: Use our AI chatbot for instant answers, email support@sahulatkar.com for detailed queries, or call our helpline at 0800-SAHULAT (7248528). Premium members get priority support.",
    category: "Support",
    icon: <Headphones className="w-5 h-5" />,
    image: "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&h=200&q=80"
  }
]

const categoryColors = {
  "Financing": "from-blue-500 to-blue-600",
  "Products": "from-orange-500 to-orange-600",
  "Shariah": "from-green-500 to-green-600",
  "Process": "from-purple-500 to-purple-600",
  "Requirements": "from-pink-500 to-pink-600",
  "Delivery": "from-yellow-500 to-yellow-600",
  "Payments": "from-red-500 to-red-600",
  "Support": "from-indigo-500 to-indigo-600"
}

export function FAQSection() {
  const [activeCategory, setActiveCategory] = useState("All")
  const [expandedItems, setExpandedItems] = useState<number[]>([])
  const [searchTerm, setSearchTerm] = useState("")

  const categories = ["All", ...Array.from(new Set(faqData.map(item => item.category)))]

  const filteredFAQs = faqData.filter(item => {
    const matchesCategory = activeCategory === "All" || item.category === activeCategory
    const matchesSearch = item.question.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         item.answer.toLowerCase().includes(searchTerm.toLowerCase())
    return matchesCategory && matchesSearch
  })

  const toggleItem = (id: number) => {
    setExpandedItems(prev => 
      prev.includes(id) 
        ? prev.filter(item => item !== id)
        : [...prev, id]
    )
  }

  return (
    <div className="theme-section py-20 relative overflow-hidden">
      {/* Background Effects */}
      <div className="absolute inset-0">
        <div className="absolute top-40 left-20 w-72 h-72 bg-orange-200 rounded-full mix-blend-multiply filter blur-xl opacity-30 animate-pulse" />
        <div className="absolute bottom-40 right-20 w-96 h-96 bg-blue-200 rounded-full mix-blend-multiply filter blur-xl opacity-30 animate-pulse animation-delay-2000" />
        <div className="absolute top-60 right-60 w-64 h-64 bg-pink-200 rounded-full mix-blend-multiply filter blur-xl opacity-30 animate-pulse animation-delay-4000" />
      </div>

      <div className="container mx-auto px-4 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl lg:text-5xl font-bold text-theme mb-4">
            Frequently Asked{" "}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-orange-500 to-pink-500">
              Questions
            </span>
          </h2>
          <p className="text-xl text-theme-muted max-w-3xl mx-auto">
            Everything you need to know about SahulatKar's halal financing solutions
          </p>
        </motion.div>

        {/* Search Bar */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, delay: 0.2 }}
          className="max-w-2xl mx-auto mb-12"
        >
          <div className="relative">
            <input
              type="text"
              placeholder="Search for answers..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full px-6 py-4 pl-12 bg-white rounded-2xl shadow-lg border border-gray-200 focus:border-orange-500 focus:outline-none focus:ring-2 focus:ring-orange-500/20 transition-all duration-300"
            />
            <HelpCircle className="absolute left-4 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
          </div>
        </motion.div>

        {/* Category Filter */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, delay: 0.3 }}
          className="flex flex-wrap justify-center gap-3 mb-12"
        >
          {categories.map((category) => (
            <button
              key={category}
              onClick={() => setActiveCategory(category)}
              className={`px-6 py-3 rounded-full font-medium transition-all duration-300 ${
                activeCategory === category
                  ? "bg-gradient-to-r from-orange-500 to-orange-600 text-white shadow-lg"
                  : "bg-white text-gray-700 hover:bg-gray-100 border border-gray-200"
              }`}
            >
              {category}
            </button>
          ))}
        </motion.div>

        {/* FAQ Items */}
        <div className="max-w-4xl mx-auto space-y-4">
          {filteredFAQs.map((item, index) => (
            <motion.div
              key={item.id}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: index * 0.1 }}
              className="theme-panel rounded-2xl shadow-lg hover:shadow-xl transition-all duration-300 overflow-hidden"
            >
              <button
                onClick={() => toggleItem(item.id)}
                className="w-full px-8 py-6 flex items-center justify-between text-left hover:bg-gray-50 transition-colors duration-200"
              >
                <div className="flex items-center space-x-4 flex-1">
                  <div className={`w-12 h-12 bg-gradient-to-br ${categoryColors[item.category as keyof typeof categoryColors]} rounded-xl flex items-center justify-center text-white flex-shrink-0`}>
                    {item.icon}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-gray-900 mb-1">{item.question}</h3>
                    <span className="text-sm text-gray-500 bg-gray-100 px-3 py-1 rounded-full inline-block">
                      {item.category}
                    </span>
                  </div>
                </div>
                <div className="ml-4">
                  {expandedItems.includes(item.id) ? (
                    <ChevronUp className="w-5 h-5 text-orange-500" />
                  ) : (
                    <ChevronDown className="w-5 h-5 text-gray-400" />
                  )}
                </div>
              </button>

              <AnimatePresence>
                {expandedItems.includes(item.id) && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.3 }}
                    className="overflow-hidden"
                  >
                    <div className="px-8 pb-6 text-gray-600 leading-relaxed">
                      {item.answer}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  )
}
