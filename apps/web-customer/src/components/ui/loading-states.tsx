"use client"

import { motion } from "framer-motion"
import { Loader2, Package, CreditCard, User, ShoppingBag } from "lucide-react"

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export function LoadingSpinner({ size = 'md', className = "" }: LoadingSpinnerProps) {
  const sizeClasses = {
    sm: "w-4 h-4",
    md: "w-6 h-6", 
    lg: "w-8 h-8"
  }

  return (
    <div className={`flex items-center justify-center ${className}`}>
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
        className={`${sizeClasses[size]} text-orange-600`}
      >
        <Loader2 className="w-full h-full" />
      </motion.div>
    </div>
  )
}

interface SkeletonProps {
  className?: string
  children?: React.ReactNode
}

export function Skeleton({ className = "", children }: SkeletonProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className={`bg-gray-200 rounded-lg animate-pulse ${className}`}
    >
      {children}
    </motion.div>
  )
}

export function ProductCardSkeleton() {
  return (
    <div className="border border-gray-200 rounded-xl p-6">
      <Skeleton className="aspect-square mb-4" />
      <Skeleton className="h-4 w-3/4 mb-2" />
      <Skeleton className="h-4 w-1/2 mb-4" />
      <Skeleton className="h-10 w-full" />
    </div>
  )
}

export function OrderCardSkeleton() {
  return (
    <div className="border border-gray-200 rounded-xl p-6">
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <Skeleton className="h-5 w-48 mb-2" />
          <Skeleton className="h-4 w-32" />
        </div>
        <Skeleton className="h-6 w-20" />
      </div>
      <div className="grid grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i}>
            <Skeleton className="h-3 w-16 mb-1" />
            <Skeleton className="h-4 w-20" />
          </div>
        ))}
      </div>
    </div>
  )
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="border border-gray-200 rounded-lg p-4">
          <div className="flex items-center space-x-4">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-6 w-16" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function PageLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-orange-50">
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.5 }}
        className="text-center"
      >
        <div className="w-20 h-20 bg-gradient-to-br from-orange-500 to-orange-600 rounded-2xl flex items-center justify-center mx-auto mb-6">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
          >
            <Loader2 className="w-10 h-10 text-white" />
          </motion.div>
        </div>
        <h2 className="text-xl font-semibold text-gray-900 mb-2">Loading...</h2>
        <p className="text-gray-600">Please wait while we prepare your experience</p>
      </motion.div>
    </div>
  )
}

export function SectionLoader({ message = "Loading..." }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12">
      <LoadingSpinner size="lg" />
      <p className="text-gray-600 mt-4">{message}</p>
    </div>
  )
}
