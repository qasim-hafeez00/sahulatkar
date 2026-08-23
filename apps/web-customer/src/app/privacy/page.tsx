export default function PrivacyPage() {
  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto max-w-3xl px-4">
        <h1 className="text-3xl font-bold text-theme mb-2">Privacy Policy</h1>
        <p className="text-xs uppercase tracking-wide text-orange-500 font-semibold mb-8">
          Draft — pending legal review
        </p>

        <div className="space-y-8 text-sm text-theme-muted leading-relaxed">
          <section>
            <h2 className="text-base font-bold text-theme mb-2">What we collect</h2>
            <p>
              To assess credit and comply with KYC regulations, we collect your phone number, legal
              name, CNIC, date of birth, address, a liveness-verification video, and the products
              and orders you finance through the platform.
            </p>
          </section>
          <section>
            <h2 className="text-base font-bold text-theme mb-2">How it&apos;s protected</h2>
            <p>
              Your CNIC is encrypted at rest with AES-256-GCM before it ever touches disk. Access to
              decrypt it is restricted to the KYC review flow.
            </p>
          </section>
          <section>
            <h2 className="text-base font-bold text-theme mb-2">Who we share it with</h2>
            <p>
              Identity data is shared only with the verification providers required to approve your
              account (CNIC verification and liveness/fraud screening) and, for a purchase, the
              payment processor handling your transaction. We do not sell your data.
            </p>
          </section>
          <section>
            <h2 className="text-base font-bold text-theme mb-2">Your choices</h2>
            <p>
              You can review and update your profile information from your account settings, and
              opt in or out of marketing and push notifications from Notification preferences.
            </p>
          </section>
          <section>
            <h2 className="text-base font-bold text-theme mb-2">Questions</h2>
            <p>
              Reach us at <a href="mailto:privacy@sahulatkar.com" className="text-orange-500 hover:text-orange-600 font-semibold">privacy@sahulatkar.com</a> for anything about how your data is handled.
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
