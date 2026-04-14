import { MessageSquare, HelpCircle } from 'lucide-react';

export default function SupportPage() {
  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-16 / AD-17</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Support & escalations</h2>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <MessageSquare className="h-4 w-4 text-blue-500" />
            Open Tickets
          </div>
          <p className="mt-2 text-2xl font-bold text-white">34</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <HelpCircle className="h-4 w-4 text-amber-500" />
            Avg Resolution Time
          </div>
          <p className="mt-2 text-2xl font-bold text-white">4.2h</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <MessageSquare className="h-4 w-4 text-emerald-500" />
            Customer Satisfaction
          </div>
          <p className="mt-2 text-2xl font-bold text-white">4.6/5</p>
        </div>
      </div>

      <div className="rounded-2xl border border-dashed border-white/10 bg-slate-950/50 p-6 text-center">
        <p className="text-sm text-slate-400">Support ticket management and escalation workflows coming soon</p>
      </div>
    </section>
  );
}
