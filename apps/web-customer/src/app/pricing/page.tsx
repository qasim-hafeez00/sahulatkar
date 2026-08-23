import { Card, CardContent } from "@/components/ui/card"
import { CheckCircle2 } from "lucide-react"

const PLANS = [
  { months: "3", rate: "2.5%" },
  { months: "4", rate: "4.0%" },
  { months: "6", rate: "7.0%" },
  { months: "12", rate: "15.0%" },
]

export default function PricingPage() {
  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto max-w-3xl px-4">
        <h1 className="text-3xl font-bold text-theme mb-3">Pricing</h1>
        <p className="text-theme-muted mb-10 max-w-xl">
          SahulatKar doesn&apos;t charge interest. Instead, every purchase is structured as a Murabaha
          contract: we disclose the exact cost price and a fixed profit margin upfront, and that
          total never changes — no compounding, no late-payment interest, no surprise fees.
        </p>

        <Card className="card-surface mb-8">
          <CardContent className="p-6">
            <h2 className="text-lg font-bold text-theme mb-4">Financing plans</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {PLANS.map((plan) => (
                <div key={plan.months} className="rounded-2xl border border-gray-100 dark:border-white/5 p-4 text-center">
                  <p className="text-2xl font-black text-theme">{plan.months}</p>
                  <p className="text-xs text-theme-muted uppercase tracking-wide mb-2">months</p>
                  <p className="text-orange-500 font-bold">{plan.rate}</p>
                  <p className="text-[11px] text-theme-muted">profit margin</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-theme-muted mt-4">
              The exact plan and rate offered depends on the product price and your approved credit
              limit, and is shown in full — cost, profit amount, and profit percentage — before you
              sign the Murabaha contract.
            </p>
          </CardContent>
        </Card>

        <ul className="space-y-3">
          {[
            "No compounding interest — the profit amount is fixed at signing.",
            "100% of any late fee is donated to charity; SahulatKar keeps none of it.",
            "Down payment collected upfront; the rest is swept in scheduled installments.",
          ].map((line) => (
            <li key={line} className="flex items-start gap-2 text-sm text-theme-muted">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 flex-none" />
              {line}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
