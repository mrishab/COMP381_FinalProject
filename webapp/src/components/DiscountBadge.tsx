import React from 'react'
import { ArrowDownRight, ArrowUpRight, CheckCircle2 } from 'lucide-react'
import { Badge } from './ui/badge'

interface DiscountBadgeProps {
  dealStatus: 'great_deal' | 'fair_price' | 'overpriced'
  percentDiscount: number
  dollarDiscount: number
}

export const DiscountBadge: React.FC<DiscountBadgeProps> = ({
  dealStatus,
  percentDiscount,
  dollarDiscount,
}) => {
  const absDollars = Math.abs(dollarDiscount).toLocaleString()

  if (dealStatus === 'great_deal') {
    return (
      <Badge variant="success" className="px-3 py-1.5 text-xs sm:text-sm font-medium gap-1.5">
        <ArrowDownRight className="w-4 h-4 text-emerald-600" />
        <span>
          {Math.abs(percentDiscount)}% Underpriced (${absDollars} Discount)
        </span>
      </Badge>
    )
  }

  if (dealStatus === 'overpriced') {
    return (
      <Badge variant="danger" className="px-3 py-1.5 text-xs sm:text-sm font-medium gap-1.5">
        <ArrowUpRight className="w-4 h-4 text-rose-600" />
        <span>
          {Math.abs(percentDiscount)}% Above Model (${absDollars} Premium)
        </span>
      </Badge>
    )
  }

  return (
    <Badge variant="secondary" className="px-3 py-1.5 text-xs sm:text-sm font-medium gap-1.5">
      <CheckCircle2 className="w-4 h-4 text-neutral-500" />
      <span>Fairly Priced (At Model Target)</span>
    </Badge>
  )
}
