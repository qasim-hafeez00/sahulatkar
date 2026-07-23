"use client"

import { motion } from "framer-motion"
import { ArrowRight, Shield, Clock, CreditCard, Star, CheckCircle, ArrowUpRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { MovingBanner } from "@/components/ui/moving-banner"
import { ProductExtraction } from "@/components/ui/product-extraction"
import { ProductShowcase } from "@/components/ui/product-showcase"
import { FAQSection } from "@/components/ui/faq-section"
import { HeroBrandCarousel } from "@/components/ui/hero-brand-carousel"
import { FanDeckNew } from "@/components/ui/fan-deck-new"
import Link from "next/link"
import { useRouter } from "next/navigation"

export default function Home() {
  const router = useRouter()

  return (
    <div className="min-h-screen">
      {/* Fan Deck Hero Section */}
      <FanDeckNew />

      {/* Moving Banner Section */}
      <MovingBanner />

      {/* Product Extraction Section */}
      <ProductExtraction />

      {/* Product Showcase Section */}
      <ProductShowcase />

      {/* Transparent & Simple Section */}
      <section className="py-20 section-surface">
        <div className="container mx-auto px-4">
          <motion.div
            initial={{ y: 50, opacity: 0 }}
            whileInView={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.6 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <h2 className="text-4xl font-bold text-theme mb-4">
              Transparent & Simple
            </h2>
            <p className="text-xl text-theme-muted max-w-2xl mx-auto">
              Our four-step process makes getting financing quick and hassle-free
            </p>
          </motion.div>
          
          <div className="grid md:grid-cols-4 gap-8">
            {[
              { 
                step: 1, 
                title: "Sign Up", 
                description: "Create your account in minutes with instant verification",
                image: "https://cdn.pixabay.com/photo/2022/06/17/16/48/subscribe-7268360_1280.jpg"
              },
              { 
                step: 2, 
                title: "Browse Products", 
                description: "Paste any product URL from your favorite stores",
                image: "https://cdn.pixabay.com/photo/2021/03/02/13/04/laptop-6062423_640.jpg"
              },
              { 
                step: 3, 
                title: "Get Approved", 
                description: "Instant credit assessment with transparent terms",
                image: "https://cdn.pixabay.com/photo/2021/08/17/17/28/covid-19-6553695_1280.jpg"
              },
              { 
                step: 4, 
                title: "Shop Now", 
                description: "We purchase and deliver, you pay in easy installments",
                image: "https://cdn.pixabay.com/photo/2017/10/29/17/31/online-2900303_1280.jpg"
              }
            ].map((item, index) => (
              <motion.div
                key={item.step}
                initial={{ y: 50, opacity: 0 }}
                whileInView={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.6, delay: index * 0.1 }}
                viewport={{ once: true }}
              >
                <Card className="text-center p-6 border-0 card-surface hover-lift">
                  <div className="relative w-full h-32 mb-4 rounded-lg overflow-hidden">
                    <img 
                      src={item.image}
                      alt={item.title}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/40 to-transparent" />
                    <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2">
                      <div className="w-12 h-12 bg-gradient-to-br from-orange-500 to-orange-600 rounded-xl flex items-center justify-center text-white text-xl font-bold">
                        {item.step}
                      </div>
                    </div>
                  </div>
                  <h3 className="text-xl font-semibold text-theme mb-2">{item.title}</h3>
                  <p className="text-theme-muted">{item.description}</p>
                </Card>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <FAQSection />

      
      {/* Product Showcase */}
      <section className="py-20 section-surface">
        <div className="container mx-auto px-4">
          <motion.div
            initial={{ y: 50, opacity: 0 }}
            whileInView={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.6 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <h2 className="text-4xl font-bold text-theme mb-4">
              Popular Products
            </h2>
            <p className="text-xl text-theme-muted max-w-2xl mx-auto">
              See what our customers are financing with flexible payment plans
            </p>
          </motion.div>
          
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { 
                name: "iPhone 15 Pro", 
                price: "PKR 299,999", 
                monthly: "PKR 25,000",
                image: " https://cdn.pixabay.com/photo/2022/09/26/19/40/iphone-7481400_1280.jpg"
              },
              { 
                name: "MacBook Air M2", 
                price: "PKR 249,999", 
                monthly: "PKR 20,833",
                image: "https://cdn.pixabay.com/photo/2016/10/15/13/40/laptop-1742462_1280.jpg"
              },
              { 
                name: "Samsung TV 55\"", 
                price: "PKR 149,999", 
                monthly: "PKR 12,500",
                image: "https://cdn.pixabay.com/photo/2015/02/07/20/58/tv-627876_1280.jpg"
              }
            ].map((product, index) => (
              <motion.div
                key={product.name}
                initial={{ y: 50, opacity: 0 }}
                whileInView={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.6, delay: index * 0.1 }}
                viewport={{ once: true }}
              >
                <Card className="overflow-hidden border-0 card-surface hover-lift">
                  <div className="aspect-square relative overflow-hidden">
                    <img 
                      src={product.image}
                      alt={product.name}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent" />
                  </div>
                  <CardContent className="p-6">
                    <h3 className="text-xl font-semibold text-theme mb-2">{product.name}</h3>
                    <div className="flex items-center justify-between mb-4">
                      <span className="text-2xl font-bold text-theme">{product.price}</span>
                      <span className="text-sm text-green-600 font-medium">{product.monthly}/mo</span>
                    </div>
                    <Button 
                      className="w-full"
                      onClick={() => window.location.href = '/auth/login'}
                    >
                      Finance Now
                    </Button>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 bg-gradient-to-br from-orange-600 to-orange-700">
        <div className="container mx-auto px-4 text-center">
          <motion.div
            initial={{ y: 50, opacity: 0 }}
            whileInView={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.6 }}
            viewport={{ once: true }}
          >
            <h2 className="text-4xl font-bold text-white mb-6">
              Financial Freedom Awaits
            </h2>
            <p className="text-xl text-orange-100 mb-8 max-w-2xl mx-auto">
              Join thousands of satisfied customers who have found their perfect financing solution with SahulatKar
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Button 
                size="xl" 
                variant="secondary" 
                className="bg-white text-orange-600 hover:bg-gray-100"
                onClick={() => router.push('/auth/register')}
              >
                Apply Now
                <ArrowRight className="w-5 h-5 ml-2" />
              </Button>
              <Button 
                size="xl" 
                variant="ghost" 
                className="text-white border-white hover:bg-white/10"
                onClick={() => router.push('/cart')}
              >
                Learn More
              </Button>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 bg-[#231E1C] dark:bg-[#161413] text-[#F5EDE6]">
        <div className="container mx-auto px-4">
          <div className="grid md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center space-x-3 mb-4">
                <div className="w-10 h-10 bg-gradient-to-br from-orange-500 to-orange-600 rounded-xl flex items-center justify-center">
                  <span className="text-white font-bold text-xl">S</span>
                </div>
                <span className="text-2xl font-bold">SahulatKar</span>
              </div>
              <p className="text-gray-400">
                Secure Your Future with Shariah Principles
              </p>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Product</h4>
              <ul className="space-y-2 text-gray-400">
                <li><Link href="/cart" className="hover:text-white transition-colors">How It Works</Link></li>
                <li><Link href="/pricing" className="hover:text-white transition-colors">Pricing</Link></li>
                <li><Link href="/cart" className="hover:text-white transition-colors">Shop Now</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Company</h4>
              <ul className="space-y-2 text-gray-400">
                <li><Link href="/about" className="hover:text-white transition-colors">About Us</Link></li>
                <li><Link href="/careers" className="hover:text-white transition-colors">Careers</Link></li>
                <li><Link href="/contact" className="hover:text-white transition-colors">Contact</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Legal</h4>
              <ul className="space-y-2 text-gray-400">
                <li><Link href="/privacy" className="hover:text-white transition-colors">Privacy Policy</Link></li>
                <li><Link href="/terms" className="hover:text-white transition-colors">Terms of Service</Link></li>
                <li><Link href="/shariah" className="hover:text-white transition-colors">Shariah Compliance</Link></li>
              </ul>
            </div>
          </div>
          <div className="border-t border-gray-800 pt-8 text-center text-gray-400">
            <p>&copy; 2024 SahulatKar. All rights reserved. SECP Registered & Shariah Certified.</p>
          </div>
        </div>
      </footer>
    </div>
  )
}
