import * as React from "react"
import { cn } from "@/lib/utils"

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  leftIcon?: React.ReactNode
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, label, error, leftIcon, ...props }, ref) => {
    return (
      <div className="space-y-2">
        {label && (
          <label className="text-sm font-medium text-[var(--foreground)]">
            {label}
          </label>
        )}
        <div className="relative">
          {leftIcon && (
            <div className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400">
              {leftIcon}
            </div>
          )}
          <input
            type={type}
            className={cn(
              "flex h-12 w-full rounded-xl border bg-[var(--card-bg)] px-4 py-3 text-sm text-[var(--foreground)] transition-all duration-200 file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-[rgba(0,0,0,0.4)] dark:placeholder:text-[rgba(255,255,255,0.4)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50 hover:brightness-105",
              leftIcon && "pl-12",
              error && "border-red-500 focus-visible:ring-red-500",
              className
            )}
            ref={ref}
            {...props}
          />
        </div>
        {error && (
          <p className="text-sm text-red-500">{error}</p>
        )}
      </div>
    )
  }
)
Input.displayName = "Input"

export { Input }
