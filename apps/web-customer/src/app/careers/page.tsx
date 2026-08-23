import { Mail } from "lucide-react"

export default function CareersPage() {
  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto max-w-3xl px-4">
        <h1 className="text-3xl font-bold text-theme mb-3">Careers</h1>
        <p className="text-theme-muted mb-6 max-w-xl">
          We&apos;re a small team building Pakistan&apos;s first vendor-agnostic, Shariah-compliant
          BNPL platform — spanning credit risk, payments, KYC, and checkout automation. We&apos;re
          not running open postings through this site yet, but we&apos;re always glad to hear from
          people who want to work on this problem.
        </p>
        <a
          href="mailto:careers@sahulatkar.com"
          className="inline-flex items-center gap-2 font-semibold text-orange-500 hover:text-orange-600 transition-colors"
        >
          <Mail className="w-4 h-4" />
          careers@sahulatkar.com
        </a>
      </div>
    </div>
  )
}
