import * as React from "react"
import { cn } from "../../lib/utils"

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "secondary" | "outline" | "ghost"
  size?: "default" | "sm" | "lg" | "icon"
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => {
    const baseStyles =
      "inline-flex items-center justify-center whitespace-nowrap rounded-xl text-xs sm:text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-neutral-950 disabled:pointer-events-none disabled:opacity-50"

    const variants = {
      default: "bg-neutral-900 text-neutral-50 shadow hover:bg-neutral-800",
      secondary: "bg-neutral-100 text-neutral-900 hover:bg-neutral-200/80",
      outline: "border border-neutral-200/80 bg-white hover:bg-neutral-50 text-neutral-700",
      ghost: "hover:bg-neutral-100 text-neutral-700",
    }

    const sizes = {
      default: "h-9 px-4 py-2",
      sm: "h-8 rounded-lg px-3 text-xs",
      lg: "h-10 rounded-xl px-6",
      icon: "h-9 w-9",
    }

    return (
      <button
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"
