import * as React from "react"
import { cn } from "../../lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "outline" | "success" | "danger"
}

export function Badge({
  className,
  variant = "default",
  ...props
}: BadgeProps) {
  const variants = {
    default: "border-transparent bg-neutral-900 text-neutral-50 shadow",
    secondary: "border-transparent bg-neutral-100 text-neutral-800",
    outline: "text-neutral-700 border-neutral-200",
    success: "border-emerald-200/80 bg-emerald-50 text-emerald-800",
    danger: "border-rose-200/80 bg-rose-50 text-rose-800",
  }

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
        variants[variant],
        className
      )}
      {...props}
    />
  )
}
