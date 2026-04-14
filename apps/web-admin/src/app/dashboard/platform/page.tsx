import { Settings, Activity, Server } from 'lucide-react';

export default function PlatformOpsPage() {
  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-23 / AD-24 / AD-25+</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Platform operations</h2>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Activity className="h-4 w-4 text-emerald-500" />
            System Status
          </div>
          <p className="mt-2 text-2xl font-bold text-emerald-400">Operational</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Server className="h-4 w-4 text-blue-500" />
            Uptime (30d)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">99.96%</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Settings className="h-4 w-4 text-amber-500" />
            Active Workers
          </div>
          <p className="mt-2 text-2xl font-bold text-white">24</p>
        </div>
      </div>

      <div className="rounded-2xl border border-dashed border-white/10 bg-slate-950/50 p-6 text-center">
        <p className="text-sm text-slate-400">System monitoring, logs, and platform configuration coming soon</p>
      </div>
    </section>
  );
}
