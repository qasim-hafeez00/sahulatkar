import { CheckCircle2, Circle, CreditCard, Phone, Sparkles } from "lucide-react"

const steps = [
  { id: "phone", label: "Phone", icon: Phone },
  { id: "cnic-front", label: "CNIC Front", icon: CreditCard },
  { id: "cnic-back", label: "CNIC Back", icon: CreditCard },
  { id: "liveness", label: "Liveness", icon: Sparkles },
  { id: "success", label: "Success", icon: CheckCircle2 },
]

type VerificationStepperProps = {
  active: "phone" | "cnic-front" | "cnic-back" | "liveness" | "success"
}

export function VerificationStepper({ active }: VerificationStepperProps) {
  const activeIndex = steps.findIndex((s) => s.id === active)

  return (
    <div className="mt-10 glass-surface rounded-[2rem] p-5 shadow-[var(--shadow-soft)]">
      <div className="relative flex min-w-full items-center justify-between gap-2 overflow-x-auto pb-1">
        <div className="pointer-events-none absolute left-8 right-8 top-5 hidden h-0.5 bg-[var(--section-border)] sm:block" />
        <div
          className="pointer-events-none absolute left-8 top-5 hidden h-0.5 bg-gradient-to-r from-orange-500 to-orange-400 transition-all duration-500 sm:block"
          style={{ width: activeIndex <= 0 ? "0%" : `${(activeIndex / (steps.length - 1)) * 100}%`, maxWidth: "calc(100% - 4rem)" }}
        />

        {steps.map((step, index) => {
          const Icon = step.icon
          const isActive = active === step.id
          const isComplete = index < activeIndex

          return (
            <div
              key={step.id}
              className="relative flex min-w-[88px] flex-col items-center gap-2.5 text-center sm:min-w-[110px]"
            >
              <span
                className={`relative z-10 grid h-11 w-11 place-items-center rounded-2xl border text-sm transition-all duration-300 ${
                  isActive
                    ? "border-orange-500 bg-gradient-to-br from-orange-500 to-orange-600 text-white shadow-lg shadow-orange-500/30 scale-110"
                    : isComplete
                      ? "border-emerald-400/50 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                      : "border-[var(--section-border)] bg-[var(--card-bg)] text-theme-muted"
                }`}
              >
                <Icon className="h-4 w-4" />
              </span>
              <span
                className={`text-[10px] font-medium uppercase tracking-[0.28em] ${
                  isActive ? "text-theme" : "text-theme-muted"
                }`}
              >
                {step.label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
