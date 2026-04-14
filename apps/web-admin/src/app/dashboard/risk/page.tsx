import { TrendingUp, AlertTriangle } from 'lucide-react';

export default function RiskPage() {
  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-10 / AD-11 / AD-12</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Risk & fraud</h2>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            High-Risk Users
          </div>
          <p className="mt-2 text-2xl font-bold text-white">217</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <TrendingUp className="h-4 w-4 text-amber-500" />
            Fraud Alerts (24h)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">12</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <TrendingUp className="h-4 w-4 text-emerald-500" />
            Blocked Txns
          </div>
          <p className="mt-2 text-2xl font-bold text-white">4</p>
        </div>
      </div>

      <div className="rounded-2xl border border-dashed border-white/10 bg-slate-950/50 p-6 text-center">
        <p className="text-sm text-slate-400">Risk monitoring dashboard coming soon</p>
      </div>
    </section>
  );
}
