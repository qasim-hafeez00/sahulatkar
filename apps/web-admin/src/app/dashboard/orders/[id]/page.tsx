import Link from 'next/link';
import { ArrowLeft, Calendar, CreditCard, Package2, UserCircle2 } from 'lucide-react';
import { adminApi } from '@/lib/api-client';

type OrderDetailResponse = {
  id: number;
  order_number: string;
  status: string;
  user: {
    id: number;
    email: string;
    phone: string;
  };
  product: {
    name: string;
    price: number;
  };
  totals: {
    total_amount: number;
    down_payment: number;
    remaining: number;
  };
  created_at: string;
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

function formatAmount(value: number) {
  return `PKR ${value.toLocaleString()}`;
}

export default async function OrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const response = await adminApi.get<OrderDetailResponse | { error: string }>(`/admin/orders/${id}`).catch(() => null);

  if (!response || 'error' in response) {
    return (
      <section className="space-y-6">
        <Link href="/dashboard/orders" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white">
          <ArrowLeft className="h-4 w-4" />
          Back to orders
        </Link>
        <div className="glass-panel rounded-2xl p-8 text-center">
          <p className="text-sm uppercase tracking-[0.3em] text-slate-500">AD-05</p>
          <h1 className="mt-3 text-2xl font-semibold text-white">Order not found</h1>
          <p className="mt-2 text-sm text-slate-400">The requested order record is unavailable or has been removed.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <Link href="/dashboard/orders" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white">
        <ArrowLeft className="h-4 w-4" />
        Back to orders
      </Link>

      <div className="glass-panel rounded-3xl p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-05 / Order detail</p>
            <h1 className="mt-2 text-3xl font-semibold text-white">{response.order_number}</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-400">
              Financial and lifecycle overview for the selected order.
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
            <UserCircle2 className="h-4 w-4 text-blue-400" />
            Customer
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{response.user.email}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Package2 className="h-4 w-4 text-emerald-400" />
            Product
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{response.product.name}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <CreditCard className="h-4 w-4 text-amber-400" />
            Total
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{formatAmount(response.totals.total_amount)}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Calendar className="h-4 w-4 text-indigo-400" />
            Down payment
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{formatAmount(response.totals.down_payment)}</p>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="glass-panel rounded-3xl p-6 xl:col-span-2">
          <h2 className="text-lg font-semibold text-white">Order financials</h2>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Order ID</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{response.id}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Remaining</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{formatAmount(response.totals.remaining)}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Product price</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{formatAmount(response.product.price)}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Created</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{formatDate(response.created_at)}</dd>
            </div>
          </dl>
        </div>

        <div className="glass-panel rounded-3xl p-6">
          <h2 className="text-lg font-semibold text-white">Customer snapshot</h2>
          <p className="mt-4 text-sm leading-6 text-slate-400">
            {response.user.email} · {response.user.phone}
          </p>
          <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-300">
            The next iteration can add order timeline, delivery status, and payment plan actions.
          </div>
        </div>
      </div>
    </section>
  );
}
