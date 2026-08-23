export default function TermsPage() {
  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto max-w-3xl px-4">
        <h1 className="text-3xl font-bold text-theme mb-2">Terms of Service</h1>
        <p className="text-xs uppercase tracking-wide text-orange-500 font-semibold mb-8">
          Draft — pending legal review
        </p>

        <div className="space-y-8 text-sm text-theme-muted leading-relaxed">
          <section>
            <h2 className="text-base font-bold text-theme mb-2">How financing works</h2>
            <p>
              When you paste a product link, SahulatKar assesses your credit, presents a financing
              offer with the cost and profit margin disclosed in full, and — once you sign the
              Wakalah and Murabaha contracts by OTP — purchases the item on your behalf. You then
              repay in the scheduled installments shown at signing.
            </p>
          </section>
          <section>
            <h2 className="text-base font-bold text-theme mb-2">Your responsibilities</h2>
            <p>
              You agree to provide accurate identity information during KYC, to keep your account
              credentials confidential, and to make installment payments on the agreed schedule.
            </p>
          </section>
          <section>
            <h2 className="text-base font-bold text-theme mb-2">Late payments</h2>
            <p>
              A late fee may apply to a missed installment. SahulatKar does not retain any portion
              of a late fee — 100% of it is donated to charity.
            </p>
          </section>
          <section>
            <h2 className="text-base font-bold text-theme mb-2">Disputes</h2>
            <p>
              If an order arrives damaged, wrong, or undelivered, raise it through Support as soon
              as possible so we can investigate before the next installment is due.
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
