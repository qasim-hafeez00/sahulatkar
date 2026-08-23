import Link from "next/link"
import { Card, CardContent } from "@/components/ui/card"
import { Mail, LifeBuoy } from "lucide-react"

export default function ContactPage() {
  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto max-w-3xl px-4">
        <h1 className="text-3xl font-bold text-theme mb-3">Contact Us</h1>
        <p className="text-theme-muted mb-8 max-w-xl">
          For anything about an active order, payment, or KYC verification, the fastest path is
          through Support — it&apos;s tied to your account so we can see your order history.
        </p>

        <div className="grid sm:grid-cols-2 gap-4">
          <Link href="/support">
            <Card className="card-surface hover-lift h-full">
              <CardContent className="p-6 flex gap-3 items-start">
                <LifeBuoy className="w-5 h-5 text-orange-500 flex-none mt-0.5" />
                <div>
                  <h2 className="font-bold text-theme mb-1">Help &amp; Support</h2>
                  <p className="text-sm text-theme-muted">Order issues, disputes, and account questions</p>
                </div>
              </CardContent>
            </Card>
          </Link>
          <a href="mailto:hello@sahulatkar.com">
            <Card className="card-surface hover-lift h-full">
              <CardContent className="p-6 flex gap-3 items-start">
                <Mail className="w-5 h-5 text-orange-500 flex-none mt-0.5" />
                <div>
                  <h2 className="font-bold text-theme mb-1">General Inquiries</h2>
                  <p className="text-sm text-theme-muted">hello@sahulatkar.com</p>
                </div>
              </CardContent>
            </Card>
          </a>
        </div>
      </div>
    </div>
  )
}
