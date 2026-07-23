import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-[var(--accent)] text-white shadow-lg hover:shadow-xl hover:brightness-105 active:scale-[0.98]",
        destructive: "bg-red-600 text-white hover:bg-red-700",
        outline: "border-2 border-[rgba(0,0,0,0.06)] bg-[var(--card-bg)] text-[var(--foreground)] hover:brightness-105",
        secondary: "bg-[rgba(0,0,0,0.04)] dark:bg-[rgba(255,255,255,0.04)] text-[var(--foreground)] hover:brightness-105",
        ghost: "bg-transparent hover:bg-[rgba(0,0,0,0.04)] dark:hover:bg-[rgba(255,255,255,0.04)] hover:text-[var(--accent)]",
        link: "text-[var(--accent)] underline-offset-4 hover:underline",
        glass: "bg-[var(--card-bg)] backdrop-blur-md border border-[rgba(255,255,255,0.06)] text-[var(--foreground)] hover:brightness-105",
        dark: "bg-[var(--card-bg)] text-[var(--foreground)] hover:brightness-110",
      },
      size: {
        default: "h-12 px-6 py-3",
        sm: "h-10 rounded-lg px-4 text-sm",
        lg: "h-14 rounded-2xl px-8 text-base",
        icon: "h-10 w-10",
        xl: "h-16 rounded-2xl px-10 text-lg",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
