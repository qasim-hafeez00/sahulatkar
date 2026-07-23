"use client"

import React, { useState } from "react"
import { motion } from "framer-motion"
import { AlertTriangle, RefreshCw, Home, ArrowLeft, X, WifiOff, ServerCrash, FileQuestion } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
  errorInfo?: any
}

interface ErrorDisplayProps {
  error?: Error
  reset?: () => void
  type?: 'network' | 'server' | 'not-found' | 'general'
  message?: string
}

export function ErrorDisplay({ 
  error, 
  reset, 
  type = 'general', 
  message 
}: ErrorDisplayProps) {
  const getErrorIcon = () => {
    switch (type) {
      case 'network': return <WifiOff className="w-12 h-12" />
      case 'server': return <ServerCrash className="w-12 h-12" />
      case 'not-found': return <FileQuestion className="w-12 h-12" />
      default: return <AlertTriangle className="w-12 h-12" />
    }
  }

  const getErrorTitle = () => {
    switch (type) {
      case 'network': return 'Network Error'
      case 'server': return 'Server Error'
      case 'not-found': return 'Page Not Found'
      default: return 'Something went wrong'
    }
  }

  const getErrorMessage = () => {
    if (message) return message
    switch (type) {
      case 'network': return 'Please check your internet connection and try again.'
      case 'server': return 'Our servers are experiencing issues. Please try again later.'
      case 'not-found': return 'The page you are looking for does not exist.'
      default: return error?.message || 'An unexpected error occurred.'
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-orange-50 p-4">
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-md"
      >
        <Card className="border-0 shadow-large">
          <CardContent className="p-8 text-center">
            <motion.div
              initial={{ y: -20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 0.2, duration: 0.5 }}
              className="w-20 h-20 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-6 text-red-600"
            >
              {getErrorIcon()}
            </motion.div>
            
            <motion.div
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 0.4, duration: 0.5 }}
            >
              <h2 className="text-2xl font-bold text-gray-900 mb-4">
                {getErrorTitle()}
              </h2>
              <p className="text-gray-600 mb-8">
                {getErrorMessage()}
              </p>
              
              <div className="space-y-3">
                {reset && (
                  <Button
                    onClick={reset}
                    className="w-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700"
                  >
                    <RefreshCw className="w-4 h-4 mr-2" />
                    Try Again
                  </Button>
                )}
                
                <div className="grid grid-cols-2 gap-3">
                  <Button variant="outline" className="w-full">
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Go Back
                  </Button>
                  <Button variant="outline" className="w-full">
                    <Home className="w-4 h-4 mr-2" />
                    Home
                  </Button>
                </div>
              </div>
            </motion.div>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}

export function ErrorAlert({ 
  message, 
  onDismiss, 
  type = 'warning' 
}: { 
  message: string
  onDismiss?: () => void
  type?: 'error' | 'warning' | 'info' 
}) {
  const getAlertColor = () => {
    switch (type) {
      case 'error': return "bg-red-50 border-red-200 text-red-800"
      case 'warning': return "bg-orange-50 border-orange-200 text-orange-800"
      case 'info': return "bg-blue-50 border-blue-200 text-blue-800"
      default: return "bg-gray-50 border-gray-200 text-gray-800"
    }
  }

  const getIconColor = () => {
    switch (type) {
      case 'error': return "text-red-600"
      case 'warning': return "text-orange-600"
      case 'info': return "text-blue-600"
      default: return "text-gray-600"
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={`border rounded-xl p-4 ${getAlertColor()}`}
    >
      <div className="flex items-start space-x-3">
        <AlertTriangle className={`w-5 h-5 mt-0.5 flex-shrink-0 ${getIconColor()}`} />
        <div className="flex-1">
          <p className="text-sm font-medium">{message}</p>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className={`flex-shrink-0 ${getIconColor()}`}
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    </motion.div>
  )
}

export function NetworkError({ onRetry }: { onRetry?: () => void }) {
  return (
    <ErrorDisplay
      type="network"
      message="Unable to connect to our servers. Please check your internet connection and try again."
      reset={onRetry}
    />
  )
}

export function ServerError({ onRetry }: { onRetry?: () => void }) {
  return (
    <ErrorDisplay
      type="server"
      message="Our servers are temporarily unavailable. We're working to fix the issue. Please try again later."
      reset={onRetry}
    />
  )
}

export function NotFoundError() {
  return (
    <ErrorDisplay
      type="not-found"
      message="The page you're looking for doesn't exist or has been moved."
    />
  )
}

// Error Boundary Component
export class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ComponentType<{ error?: Error; reset: () => void }> },
  ErrorBoundaryState
> {
  constructor(props: any) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: any) {
    console.error('Error caught by boundary:', error, errorInfo)
    this.setState({ error, errorInfo })
  }

  reset = () => {
    this.setState({ hasError: false, error: undefined, errorInfo: undefined })
  }

  render() {
    if (this.state.hasError) {
      const FallbackComponent = this.props.fallback || ErrorDisplay
      return <FallbackComponent error={this.state.error} reset={this.reset} />
    }

    return this.props.children
  }
}

// Retry Wrapper Component
export function RetryWrapper({ 
  children, 
  retryCount = 3, 
  onRetry 
}: { 
  children: React.ReactNode
  retryCount?: number
  onRetry?: () => void 
}) {
  const [hasError, setHasError] = useState(false)
  const [attempts, setAttempts] = useState(0)

  const handleRetry = () => {
    if (attempts < retryCount) {
      setAttempts((prev: number) => prev + 1)
      setHasError(false)
      onRetry?.()
    }
  }

  if (hasError) {
    return (
      <ErrorDisplay
        message="Failed to load content. Please try again."
        reset={handleRetry}
      />
    )
  }

  return (
    <ErrorBoundary
      fallback={({ error, reset }) => (
        <ErrorDisplay
          error={error}
          reset={() => {
            reset()
            handleRetry()
          }}
        />
      )}
    >
      {children}
    </ErrorBoundary>
  )
}
