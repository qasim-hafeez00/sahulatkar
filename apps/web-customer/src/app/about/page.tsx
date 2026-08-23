import { Card, CardContent } from "@/components/ui/card"
import { ShieldCheck, Landmark, Link2 } from "lucide-react"

export default function AboutPage() {
  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto max-w-3xl px-4">
        <h1 className="text-3xl font-bold text-theme mb-3">About SahulatKar</h1>
        <p className="text-theme-muted mb-10 max-w-xl">
          SahulatKar is Pakistan&apos;s vendor-agnostic, Shariah-compliant Buy Now, Pay Later
          platform. You paste the link to any product from any online store, and we handle the
          rest — assessing your credit, purchasing the item on your behalf, and letting you repay
          in scheduled installments under a Murabaha contract.
        </p>

        <div className="grid gap-4">
          <Card className="card-surface">
            <CardContent className="p-6 flex gap-4 items-start">
              <Link2 className="w-6 h-6 text-orange-500 flex-none mt-1" />
              <div>
                <h2 className="font-bold text-theme mb-1">Vendor-agnostic</h2>
                <p className="text-sm text-theme-muted">Any store, any product URL — we&apos;re not tied to a single merchant catalogue.</p>
              </div>
            </CardContent>
          </Card>
          <Card className="card-surface">
            <CardContent className="p-6 flex gap-4 items-start">
              <ShieldCheck className="w-6 h-6 text-orange-500 flex-none mt-1" />
              <div>
                <h2 className="font-bold text-theme mb-1">Shariah-compliant by design</h2>
                <p className="text-sm text-theme-muted">Every contract discloses cost and profit upfront, with no compounding interest and 100% of late fees donated to charity.</p>
              </div>
            </CardContent>
          </Card>
          <Card className="card-surface">
            <CardContent className="p-6 flex gap-4 items-start">
              <Landmark className="w-6 h-6 text-orange-500 flex-none mt-1" />
              <div>
                <h2 className="font-bold text-theme mb-1">Registered in Pakistan</h2>
                <p className="text-sm text-theme-muted">SahulatKar (Pvt) Ltd. operates under SECP registration, with contracts reviewed for Shariah compliance.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
