"use client"

import { motion } from "framer-motion"
import {
  ArrowRight,
  UserPlus,
  Link2,
  ShieldCheck,
  PackageCheck,
  HeartHandshake,
  BadgeCheck,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { MovingBanner } from "@/components/ui/moving-banner"
import { ProductExtraction } from "@/components/ui/product-extraction"
import { ProductShowcase } from "@/components/ui/product-showcase"
import { FAQSection } from "@/components/ui/faq-section"
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
      <section id="how-it-works" className="py-20 section-surface">
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
                icon: UserPlus,
              },
              {
                step: 2,
                title: "Paste a Link",
                description: "Paste any product URL from your favorite stores",
                icon: Link2,
              },
              {
                step: 3,
                title: "Get Approved",
                description: "Instant credit assessment with transparent terms",
                icon: ShieldCheck,
              },
              {
                step: 4,
                title: "Shop Now",
                description: "We purchase and deliver, you pay in easy installments",
                icon: PackageCheck,
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
                  <div className="relative mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-orange-500 to-orange-600 shadow-lg shadow-orange-500/20">
                    <item.icon className="h-9 w-9 text-white" strokeWidth={1.75} />
                    <span className="absolute -right-2 -top-2 flex h-7 w-7 items-center justify-center rounded-full border-2 border-[var(--card-bg)] bg-[var(--foreground)] text-xs font-bold text-[var(--background)]">
                      {item.step}
                    </span>
                  </div>
                  <h3 className="text-xl font-semibold text-theme mb-2">{item.title}</h3>
                  <p className="text-theme-muted">{item.description}</p>
                </Card>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Shariah Compliance & Trust Section */}
      <section id="shariah-compliance" className="py-20 section-surface">
        <div className="container mx-auto px-4">
          <motion.div
            initial={{ y: 50, opacity: 0 }}
            whileInView={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.6 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <h2 className="text-4xl font-bold text-theme mb-4">
              Shariah Compliance &amp; Trust
            </h2>
            <p className="text-xl text-theme-muted max-w-2xl mx-auto">
              Every contract, fee, and profit margin is disclosed upfront and structured under a Murabaha agreement
            </p>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: ShieldCheck,
                title: "Fully Transparent Pricing",
                description: "The cost price, profit amount, and profit percentage are disclosed on every contract before you sign — no hidden markups.",
              },
              {
                icon: HeartHandshake,
                title: "100% of Late Fees to Charity",
                description: "We don't profit from missed payments. Every late fee collected is donated in full — none of it is retained by SahulatKar.",
              },
              {
                icon: BadgeCheck,
                title: "SECP Registered & Certified",
                description: "SahulatKar operates as a registered entity under Pakistani law, with every Murabaha contract reviewed for Shariah compliance.",
              },
            ].map((item, index) => (
              <motion.div
                key={item.title}
                initial={{ y: 50, opacity: 0 }}
                whileInView={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.6, delay: index * 0.1 }}
                viewport={{ once: true }}
              >
                <Card className="text-center p-6 border-0 card-surface hover-lift h-full">
                  <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-orange-500 to-orange-600 shadow-lg shadow-orange-500/20">
                    <item.icon className="h-8 w-8 text-white" strokeWidth={1.75} />
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
      <div id="faq">
        <FAQSection />
      </div>

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
                <li><Link href="/#how-it-works" className="hover:text-white transition-colors">How It Works</Link></li>
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
                <li><Link href="/#shariah-compliance" className="hover:text-white transition-colors">Shariah Compliance</Link></li>
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
