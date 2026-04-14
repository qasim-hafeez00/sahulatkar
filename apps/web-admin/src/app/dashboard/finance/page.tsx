import { DollarSign, TrendingDown, TrendingUp } from 'lucide-react';

export default function FinancePage() {
  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-13 / AD-14 / AD-15</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Finance & reporting</h2>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <DollarSign className="h-4 w-4 text-emerald-500" />
            Total Revenue (MTD)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">PKR 45.2M</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <TrendingUp className="h-4 w-4 text-blue-500" />
            Profit Margin
          </div>
          <p className="mt-2 text-2xl font-bold text-white">12.5%</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <TrendingDown className="h-4 w-4 text-amber-500" />
            Outstanding Receivables
          </div>
          <p className="mt-2 text-2xl font-bold text-white">PKR 8.9M</p>
        </div>
      </div>

      <div className="rounded-2xl border border-dashed border-white/10 bg-slate-950/50 p-6 text-center">
        <p className="text-sm text-slate-400">Finance reporting dashboard & reconciliation views coming soon</p>
      </div>
    </section>
  );
}
