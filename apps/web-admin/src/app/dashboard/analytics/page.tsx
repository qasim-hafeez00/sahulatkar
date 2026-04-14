import { BarChart3, TrendingUp } from 'lucide-react';

export default function AnalyticsPage() {
  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-20 / AD-21 / AD-22</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Analytics & insights</h2>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <TrendingUp className="h-4 w-4 text-emerald-500" />
            Growth Rate (MoM)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">+18.5%</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <BarChart3 className="h-4 w-4 text-blue-500" />
            Avg Order Value
          </div>
          <p className="mt-2 text-2xl font-bold text-white">PKR 35.2K</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <TrendingUp className="h-4 w-4 text-purple-500" />
            Repeat Customer Rate
          </div>
          <p className="mt-2 text-2xl font-bold text-white">42%</p>
        </div>
      </div>

      <div className="rounded-2xl border border-dashed border-white/10 bg-slate-950/50 p-6 text-center">
        <p className="text-sm text-slate-400">Advanced analytics and custom reporting dashboard coming soon</p>
      </div>
    </section>
  );
}
