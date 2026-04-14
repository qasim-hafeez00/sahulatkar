import Link from 'next/link';
import { ArrowLeft, Calendar, Landmark, ReceiptText, TriangleAlert } from 'lucide-react';
import { adminApi } from '@/lib/api-client';

type PaymentDetailResponse = {
  id: number;
  transaction_id: string;
  order_id: number;
  amount: number;
  currency: string;
  status: string;
  method: string;
  gateway: string;
  created_at: string;
  settled_at: string | null;
  error?: {
    code: string | null;
    message: string | null;
  } | null;
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

function formatAmount(currency: string, value: number) {
  return `${currency} ${value.toLocaleString()}`;
}

export default async function PaymentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const response = await adminApi.get<PaymentDetailResponse | { error: string }>(`/admin/payments/${id}`).catch(() => null);

  if (!response || 'error' in response) {
    return (
      <section className="space-y-6">
        <Link href="/dashboard/payments" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white">
          <ArrowLeft className="h-4 w-4" />
          Back to payments
        </Link>
        <div className="glass-panel rounded-2xl p-8 text-center">
          <p className="text-sm uppercase tracking-[0.3em] text-slate-500">AD-07</p>
          <h1 className="mt-3 text-2xl font-semibold text-white">Payment not found</h1>
          <p className="mt-2 text-sm text-slate-400">The requested payment record is unavailable or has been removed.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <Link href="/dashboard/payments" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white">
        <ArrowLeft className="h-4 w-4" />
        Back to payments
      </Link>

      <div className="glass-panel rounded-3xl p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-07 / Payment detail</p>
            <h1 className="mt-2 text-3xl font-semibold text-white">{response.transaction_id}</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-400">
              Settlement, gateway and operational view of the selected transaction.
            </p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
            <div>Status: {response.status}</div>
            <div className="text-slate-500">Created {formatDate(response.created_at)}</div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <ReceiptText className="h-4 w-4 text-blue-400" />
            Amount
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{formatAmount(response.currency, response.amount)}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Landmark className="h-4 w-4 text-emerald-400" />
            Gateway
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{response.gateway}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Calendar className="h-4 w-4 text-amber-400" />
            Settled at
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{formatDate(response.settled_at)}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <TriangleAlert className="h-4 w-4 text-red-400" />
            Method
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{response.method}</p>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="glass-panel rounded-3xl p-6 xl:col-span-2">
          <h2 className="text-lg font-semibold text-white">Transaction metadata</h2>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Payment ID</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{response.id}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Order ID</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{response.order_id}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Created</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{formatDate(response.created_at)}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Settled</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{formatDate(response.settled_at)}</dd>
            </div>
          </dl>
        </div>

        <div className="glass-panel rounded-3xl p-6">
          <h2 className="text-lg font-semibold text-white">Failure details</h2>
          {response.error ? (
            <div className="mt-4 rounded-2xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-200">
              <div className="font-semibold">{response.error.code ?? 'Unknown error'}</div>
              <div className="mt-2 text-red-100/80">{response.error.message ?? 'No error message available.'}</div>
            </div>
          ) : (
            <p className="mt-4 text-sm leading-6 text-slate-400">
              No payment error was recorded for this transaction.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
