import { cn, formatCurrency } from "@/lib/utils"

interface MonthlyMoneyProps {
  /** Monthly installment amount — shown large, leading with what the user actually pays each month. */
  monthly: number
  /** Full one-time price — shown small and secondary, for context rather than as the headline number. */
  total?: number
  className?: string
}

/**
 * Leads with the monthly payment rather than the full price (financial framing: people
 * think in monthly terms, not lump sums) — used anywhere an installment amount is shown.
 */
export function MonthlyMoney({ monthly, total, className }: MonthlyMoneyProps) {
  return (
    <div className={cn("flex items-baseline gap-2", className)}>
      <span className="text-2xl font-bold text-theme">{formatCurrency(monthly)}</span>
      <span className="text-sm text-theme-muted">/mo</span>
      {total !== undefined && (
        <span className="ml-1 text-xs text-theme-muted">
          &middot; {formatCurrency(total)} total
        </span>
      )}
    </div>
  )
}
