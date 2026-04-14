import { CheckCircle, AlertCircle } from 'lucide-react';

export default function CompliancePage() {
  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-18 / AD-19</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Compliance & audit</h2>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <CheckCircle className="h-4 w-4 text-emerald-500" />
            Shariah Compliance Score
          </div>
          <p className="mt-2 text-2xl font-bold text-white">98.7%</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <AlertCircle className="h-4 w-4 text-amber-500" />
            Pending Audits
          </div>
          <p className="mt-2 text-2xl font-bold text-white">2</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <CheckCircle className="h-4 w-4 text-blue-500" />
            Last Audit Date
          </div>
          <p className="mt-2 text-2xl font-bold text-white">Apr 10</p>
        </div>
      </div>

      <div className="rounded-2xl border border-dashed border-white/10 bg-slate-950/50 p-6 text-center">
        <p className="text-sm text-slate-400">Compliance tracking and audit logs coming soon</p>
      </div>
    </section>
  );
}
