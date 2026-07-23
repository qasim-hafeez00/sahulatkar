import { BookOpen, LifeBuoy, Shield, Zap } from "lucide-react";

const ROLE_GUIDE = [
  { role: "Super Admin", scope: "Full platform access — all 35 modules, role assignment, system configuration." },
  { role: "Operations Manager", scope: "Users, Orders, Payments, HITL Queue, Merchants, System Settings, Logs." },
  { role: "Risk Officer", scope: "Risk & Fraud (alerts, underwriting, blacklist), analytics reporting." },
  { role: "Compliance Officer", scope: "Compliance & audit trail, KYC review, document verification." },
  { role: "Finance Analyst", scope: "Finance, Shariah compliance, reconciliation, financial reporting." },
  { role: "CS Agent", scope: "Users (read), Orders (read), Support tickets, document verification." },
  { role: "Analyst", scope: "Cross-functional analytics, risk reporting, cohorts and funnels." },
  { role: "Marketing Manager", scope: "Analytics, Merchants, Marketing & Growth campaigns." },
];

const MODULE_GROUPS = [
  { group: "Command Center", modules: ["Dashboard Home"] },
  { group: "Operations", modules: ["Users", "Orders", "Payments", "HITL Queue"] },
  { group: "Risk", modules: ["Risk Alerts", "Manual Underwriting", "Blacklist & Monitoring"] },
  { group: "Finance", modules: ["Finance", "Shariah Compliance", "Reconciliation"] },
  { group: "Support", modules: ["Support Tickets", "Ticket Detail"] },
  { group: "Compliance", modules: ["Compliance", "Audit Trail", "KYC Review"] },
  { group: "Analytics", modules: ["Analytics", "Cohorts & Funnels", "Custom Reports"] },
  { group: "Platform", modules: ["Merchants", "Team & Access", "System Settings", "Platform Operations", "System Health"] },
  { group: "Growth & Tools", modules: ["Marketing & Growth", "API & Developer Tools", "Notification Center", "Document Management", "Logs & Audit Trail", "Reporting Engine"] },
];

export default function HelpPage() {
  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-35</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Help &amp; documentation</h2>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="glass-panel rounded-[2rem] p-5">
          <div className="mb-4 flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-blue-400" />
            <h3 className="text-lg font-semibold text-white">Module guide</h3>
          </div>
          <p className="text-sm text-slate-400">
            The sidebar groups admin functionality into 9 sections spanning 35 module entries.
            Modules you don&apos;t have permission for are hidden automatically based on your assigned role.
          </p>
          <div className="mt-4 space-y-3">
            {MODULE_GROUPS.map((g) => (
              <div key={g.group} className="rounded-xl bg-white/5 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-amber-300">{g.group}</p>
                <p className="mt-1 text-sm text-slate-300">{g.modules.join(" · ")}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="glass-panel rounded-[2rem] p-5">
          <div className="mb-4 flex items-center gap-2">
            <Shield className="h-5 w-5 text-purple-400" />
            <h3 className="text-lg font-semibold text-white">Role reference</h3>
          </div>
          <p className="text-sm text-slate-400">
            Your role determines which modules and actions are available. Roles are assigned by a Super Admin
            in Team &amp; Access.
          </p>
          <div className="mt-4 space-y-2">
            {ROLE_GUIDE.map((r) => (
              <div key={r.role} className="rounded-xl bg-white/5 p-3">
                <p className="text-sm font-semibold text-white">{r.role}</p>
                <p className="mt-1 text-xs text-slate-400">{r.scope}</p>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="glass-panel rounded-[2rem] p-5">
        <div className="mb-4 flex items-center gap-2">
          <Zap className="h-5 w-5 text-amber-400" />
          <h3 className="text-lg font-semibold text-white">Key concepts</h3>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <div className="rounded-xl bg-white/5 p-4">
            <p className="text-sm font-semibold text-white">Critical actions</p>
            <p className="mt-1 text-xs text-slate-400">
              Destructive operations (suspending users, blacklisting, large credit-limit increases, refunds,
              restructuring) are tagged as critical and surface in the Compliance module&apos;s critical action feed
              for oversight.
            </p>
          </div>
          <div className="rounded-xl bg-white/5 p-4">
            <p className="text-sm font-semibold text-white">Manager approvals</p>
            <p className="mt-1 text-xs text-slate-400">
              Credit-limit increases above PKR 100,000 require a second admin&apos;s approval before taking
              effect. You cannot approve your own requests.
            </p>
          </div>
          <div className="rounded-xl bg-white/5 p-4">
            <p className="text-sm font-semibold text-white">Session security</p>
            <p className="mt-1 text-xs text-slate-400">
              Only one active session is permitted per admin account. Logging in elsewhere immediately revokes
              your other sessions. MFA is mandatory for all admin accounts.
            </p>
          </div>
          <div className="rounded-xl bg-white/5 p-4">
            <p className="text-sm font-semibold text-white">Data privacy</p>
            <p className="mt-1 text-xs text-slate-400">
              Account closures anonymize rather than delete customer data, with a 30-day cooling-off period
              before execution — preserving ledger and order history integrity.
            </p>
          </div>
          <div className="rounded-xl bg-white/5 p-4">
            <p className="text-sm font-semibold text-white">Shariah compliance</p>
            <p className="mt-1 text-xs text-slate-400">
              Late fees are not retained as platform revenue — they are allocated to registered charity
              organizations and tracked through the Finance and Compliance modules.
            </p>
          </div>
          <div className="rounded-xl bg-white/5 p-4">
            <p className="text-sm font-semibold text-white">Audit trail</p>
            <p className="mt-1 text-xs text-slate-400">
              Every admin action is recorded with the acting admin, target, and change details — visible in
              Compliance → Audit Trail.
            </p>
          </div>
        </div>
      </section>

      <section className="glass-panel rounded-[2rem] p-5">
        <div className="mb-4 flex items-center gap-2">
          <LifeBuoy className="h-5 w-5 text-emerald-400" />
          <h3 className="text-lg font-semibold text-white">Need help?</h3>
        </div>
        <p className="text-sm text-slate-400">
          For access issues, contact a Super Admin via Team &amp; Access. For platform bugs or feature requests,
          use the internal engineering support channel. For urgent production incidents, escalate through your
          team&apos;s on-call process.
        </p>
      </section>
    </section>
  );
}
