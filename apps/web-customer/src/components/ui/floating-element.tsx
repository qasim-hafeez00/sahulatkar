"use client"

import { motion } from "framer-motion"
import { ReactNode } from "react"

interface FloatingElementProps {
  children: ReactNode
  duration?: number
  delay?: number
  distance?: number
  className?: string
}

export function FloatingElement({ 
  children, 
  duration = 3, 
  delay = 0, 
  distance = 10,
  className = "" 
}: FloatingElementProps) {
  return (
    <motion.div
      animate={{
        y: [-distance, distance, -distance],
      }}
      transition={{
        duration,
        repeat: Infinity,
        ease: "easeInOut",
        delay,
      }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

interface PulseElementProps {
  children: ReactNode
  duration?: number
  delay?: number
  className?: string
}

export function PulseElement({ 
  children, 
  duration = 2, 
  delay = 0,
  className = "" 
}: PulseElementProps) {
  return (
    <motion.div
      animate={{
        scale: [1, 1.05, 1],
        opacity: [1, 0.8, 1],
      }}
      transition={{
        duration,
        repeat: Infinity,
        ease: "easeInOut",
        delay,
      }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

interface GlowElementProps {
  children: ReactNode
  color?: string
  intensity?: number
  className?: string
}

export function GlowElement({ 
  children, 
  color = "rgba(249, 115, 22, 0.3)",
  intensity = 30,
  className = "" 
}: GlowElementProps) {
  return (
    <motion.div
      animate={{
        boxShadow: [
          `0 0 ${intensity}px ${color}`,
          `0 0 ${intensity * 2}px ${color}`,
          `0 0 ${intensity}px ${color}`,
        ],
      }}
      transition={{
        duration: 2,
        repeat: Infinity,
        ease: "easeInOut",
      }}
      className={className}
    >
      {children}
    </motion.div>
  )
}
