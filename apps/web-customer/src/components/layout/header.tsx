"use client"

import { motion, useMotionValue, useSpring } from "framer-motion"
import { useState, useEffect } from "react"
import { Menu, X, Sun, Moon, LogOut, User as UserIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import Link from "next/link"
import { useRouter, usePathname } from "next/navigation"
import { useTheme } from "@/components/theme/theme-provider"
import { hasClientSession } from "@/lib/api-client"
import { useAuth } from "@/components/auth/auth-guard"
import { NotificationSystem } from "@/components/notifications/notification-system"

export function Header() {
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const { theme, toggleTheme } = useTheme()
  const { logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    setIsAuthenticated(hasClientSession())
  }, [pathname])

  // Mouse-following orange effect
  const mouseX = useMotionValue(0)
  const mouseY = useMotionValue(0)
  
  const springConfig = { damping: 25, stiffness: 700 }
  const translateX = useSpring(mouseX, springConfig)
  const translateY = useSpring(mouseY, springConfig)

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const rect = document.body.getBoundingClientRect()
      mouseX.set(e.clientX - rect.left)
      mouseY.set(e.clientY - rect.top)
    }

    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [mouseX, mouseY])

  return (
    <>
      {/* Mouse-following orange background effect */}
      <motion.div
        style={{
          translateX: translateX,
          translateY: translateY,
        }}
        className="fixed top-0 left-0 w-32 h-32 bg-gradient-to-br from-orange-400 to-orange-600 rounded-full blur-3xl opacity-30 dark:opacity-15 pointer-events-none z-40"
      />
      
      <motion.header
        initial={{ y: -100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="fixed top-0 left-0 right-0 z-50 pointer-events-none"
      >
        <div className="w-full rounded-b-3xl border-b border-white/25 dark:border-white/10 bg-white/20 dark:bg-black/30 backdrop-blur-3xl shadow-[0_20px_50px_rgba(249,115,22,0.05)] dark:shadow-[0_30px_70px_rgba(0,0,0,0.45)] ring-1 ring-white/10 dark:ring-white/5 transition-all duration-300 pointer-events-auto overflow-hidden">
          <div className="mx-auto max-w-7xl px-6 h-20 flex items-center justify-between">
            {/* Logo */}
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.2, duration: 0.5 }}
              className="flex items-center"
            >
              <Link href="/" className="flex items-center space-x-3 group/logo">
                <div className="w-10 h-10 bg-gradient-to-br from-orange-500 to-orange-600 rounded-xl flex items-center justify-center shadow-md shadow-orange-500/10 group-hover/logo:scale-105 transition-transform duration-300">
                  <span className="text-white font-bold text-xl">S</span>
                </div>
                <span className="text-xl font-bold tracking-tight text-[var(--foreground)] group-hover/logo:text-orange-500 transition-colors duration-300">SahulatKar</span>
              </Link>
            </motion.div>

            {/* Desktop Navigation */}
            <nav className="hidden lg:flex items-center space-x-1.5 text-[var(--foreground)]">
              {[
                { label: "Home", href: "/" },
                { label: "Shop", href: "/cart" },
                { label: "Repayments", href: "/repayment" },
                { label: "Dashboard", href: "/dashboard" },
                { label: "Support", href: "/support" },
              ].map((link, idx) => (
                <motion.div
                  key={link.label}
                  initial={{ y: -20, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ delay: 0.05 * (idx + 1), duration: 0.5 }}
                >
                  <Link 
                    href={link.href} 
                    className="relative px-4 py-2 text-sm font-semibold tracking-wide text-[var(--foreground)] hover:text-orange-500 transition-colors duration-200 ease-out group"
                  >
                    {link.label}
                    <span className="absolute bottom-0.5 left-4 right-4 h-[2px] bg-orange-500 origin-bottom scale-x-0 group-hover:scale-x-100 transition-transform duration-300 ease-out" />
                  </Link>
                </motion.div>
              ))}
            </nav>

            {/* CTA Buttons */}
            <motion.div
              initial={{ x: 20, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              transition={{ delay: 0.4, duration: 0.5 }}
              className="hidden lg:flex items-center space-x-4"
            >
              <button
                type="button"
                aria-label="Toggle theme"
                onClick={toggleTheme}
                className="border border-slate-200/50 dark:border-white/5 bg-white/50 dark:bg-white/5 flex items-center justify-center w-9 h-9 rounded-xl hover:bg-orange-500/5 hover:border-orange-500/30 text-[var(--foreground)] hover:text-orange-500 transition-all duration-200"
              >
                {theme === "dark" ? (
                  <Sun className="w-4.5 h-4.5 text-yellow-400 animate-pulse" />
                ) : (
                  <Moon className="w-4.5 h-4.5 text-orange-600" />
                )}
              </button>

              {isAuthenticated ? (
                <>
                  <NotificationSystem />
                  <button
                    type="button"
                    aria-label="Profile"
                    onClick={() => router.push('/profile')}
                    className="border border-slate-200/50 dark:border-white/5 bg-white/50 dark:bg-white/5 flex items-center justify-center w-9 h-9 rounded-xl hover:bg-orange-500/5 hover:border-orange-500/30 text-[var(--foreground)] hover:text-orange-500 transition-all duration-200"
                  >
                    <UserIcon className="w-4.5 h-4.5" />
                  </button>
                  <Button
                    variant="ghost"
                    className="text-theme hover:text-red-600 hover:bg-red-500/5 font-semibold btn-smooth rounded-xl"
                    onClick={() => logout()}
                  >
                    <LogOut className="w-4 h-4 mr-1.5" /> Log Out
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="ghost"
                    className="text-theme hover:text-orange-600 hover:bg-orange-500/5 font-semibold btn-smooth rounded-xl"
                    onClick={() => router.push('/auth/login')}
                  >
                    Sign In
                  </Button>
                  <Button
                    className="bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white font-semibold shadow-md shadow-orange-500/10 hover:shadow-orange-500/25 active:scale-[0.98] transition-all duration-300 rounded-xl px-5"
                    onClick={() => router.push('/auth/register')}
                  >
                    Get Started
                  </Button>
                </>
              )}
            </motion.div>

            {/* Mobile Menu Button */}
            <motion.button
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5, duration: 0.3 }}
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              className="lg:hidden p-2 rounded-xl border border-slate-200/50 dark:border-white/5 bg-white/50 dark:bg-white/5 text-[var(--foreground)] hover:bg-orange-500/5 transition-colors"
            >
              {isMenuOpen ? (
                <X className="w-5 h-5 text-[var(--foreground)]" />
              ) : (
                <Menu className="w-5 h-5 text-[var(--foreground)]" />
              )}
            </motion.button>
          </div>

          {/* Mobile Menu */}
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{
              height: isMenuOpen ? "auto" : 0,
              opacity: isMenuOpen ? 1 : 0,
            }}
            transition={{ duration: 0.3 }}
            className="overflow-hidden lg:hidden border-t border-slate-200/50 dark:border-white/5"
          >
            <div className="py-4 px-6 space-y-4">
              {[
                { label: "Home", href: "/" },
                { label: "Shop", href: "/cart" },
                { label: "Repayments", href: "/repayment" },
                { label: "Dashboard", href: "/dashboard" },
                { label: "Support", href: "/support" },
                ...(isAuthenticated ? [{ label: "Profile", href: "/profile" }, { label: "Notifications", href: "/notifications" }] : []),
              ].map((link) => (
                <Link
                  key={link.label}
                  href={link.href}
                  className="block font-semibold hover:text-orange-500 transition-colors"
                  onClick={() => setIsMenuOpen(false)}
                >
                  {link.label}
                </Link>
              ))}

              <div className="pt-4 border-t border-slate-200/40 dark:border-white/5 space-y-3">
                {isAuthenticated ? (
                  <Button
                    variant="ghost"
                    className="w-full justify-center text-red-600 hover:text-red-700 hover:bg-red-500/5 font-semibold rounded-xl"
                    onClick={() => {
                      setIsMenuOpen(false)
                      logout()
                    }}
                  >
                    <LogOut className="w-4 h-4 mr-1.5" /> Log Out
                  </Button>
                ) : (
                  <Button
                    variant="ghost"
                    className="w-full justify-center text-slate-800 dark:text-slate-200 hover:text-orange-500 hover:bg-orange-500/5 font-semibold rounded-xl"
                    onClick={() => {
                      router.push('/auth/login')
                      setIsMenuOpen(false)
                    }}
                  >
                    Sign In
                  </Button>
                )}

                <div className="flex items-center gap-3">
                  {!isAuthenticated && (
                  <Button
                    className="flex-1 bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white font-semibold shadow-md shadow-orange-500/10 rounded-xl"
                    onClick={() => {
                      router.push('/auth/register')
                      setIsMenuOpen(false)
                    }}
                  >
                    Get Started
                  </Button>
                  )}

                  <button
                    type="button"
                    aria-label="Toggle theme"
                    onClick={() => {
                      toggleTheme()
                      setIsMenuOpen(false)
                    }}
                    className="border border-slate-200/50 dark:border-white/5 flex items-center justify-center w-10 h-10 rounded-xl hover:bg-orange-500/5 text-[var(--foreground)]"
                  >
                    {theme === "dark" ? <Sun className="w-5 h-5 text-yellow-400" /> : <Moon className="w-5 h-5 text-orange-600" />}
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </motion.header>
    </>
  )
}
