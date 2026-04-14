import Link from 'next/link';
import { ArrowLeft, Calendar, FileSearch, UserCog, Workflow } from 'lucide-react';
import { adminApi } from '@/lib/api-client';

type HitlDetailResponse = {
  id: number;
  uuid: string;
  order_id: number;
  execution_id: number | null;
  priority: number;
  assigned_to: number | null;
  status: string;
  failure_reason: string | null;
  screenshot_s3: string | null;
  resolution: string | null;
  claimed_at: string | null;
  in_progress_at: string | null;
  resolved_at: string | null;
  sla_deadline: string | null;
};

function formatDate(value: string | null) {
  if (!value) return 'None';
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export default async function HITLDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const response = await adminApi.get<HitlDetailResponse>(`/admin/hitl/queue/${id}`).catch(() => null);

  if (!response) {
    return (
      <section className="space-y-6">
        <Link href="/dashboard/hitl" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white">
          <ArrowLeft className="h-4 w-4" />
          Back to queue
        </Link>
        <div className="glass-panel rounded-2xl p-8 text-center">
          <p className="text-sm uppercase tracking-[0.3em] text-slate-500">AD-09</p>
          <h1 className="mt-3 text-2xl font-semibold text-white">HITL case not found</h1>
          <p className="mt-2 text-sm text-slate-400">The requested queue record is unavailable or has been removed.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <Link href="/dashboard/hitl" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white">
        <ArrowLeft className="h-4 w-4" />
        Back to queue
      </Link>

      <div className="glass-panel rounded-3xl p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-09 / Case detail</p>
            <h1 className="mt-2 text-3xl font-semibold text-white">{response.uuid}</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-400">
              Human-in-the-loop case profile with resolution and SLA visibility.
            </p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
            <div>Status: {response.status}</div>
            <div className="text-slate-500">Priority {response.priority}</div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Workflow className="h-4 w-4 text-blue-400" />
            Order ID
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{response.order_id}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <UserCog className="h-4 w-4 text-emerald-400" />
            Assigned to
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{response.assigned_to ?? 'Unassigned'}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Calendar className="h-4 w-4 text-amber-400" />
            SLA deadline
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{formatDate(response.sla_deadline)}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <FileSearch className="h-4 w-4 text-red-400" />
            Resolution
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{response.resolution ?? 'Open'}</p>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="glass-panel rounded-3xl p-6 xl:col-span-2">
          <h2 className="text-lg font-semibold text-white">Timeline</h2>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Claimed at</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{formatDate(response.claimed_at)}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">In progress at</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{formatDate(response.in_progress_at)}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Resolved at</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{formatDate(response.resolved_at)}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Execution ID</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{response.execution_id ?? 'None'}</dd>
            </div>
          </dl>
        </div>

        <div className="glass-panel rounded-3xl p-6">
          <h2 className="text-lg font-semibold text-white">Failure reason</h2>
          <p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-slate-400">
            {response.failure_reason || 'No failure reason recorded.'}
          </p>
          {response.screenshot_s3 ? (
            <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-300">
              Evidence stored at {response.screenshot_s3}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
