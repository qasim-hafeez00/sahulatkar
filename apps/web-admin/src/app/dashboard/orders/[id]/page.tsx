import Link from 'next/link';
import { ArrowLeft, Calendar, CreditCard, MessageSquare, Package2, UserCircle2 } from 'lucide-react';
import { adminApiServer, GatewayRequestError } from '@/lib/admin-api-server';
import { ErrorBanner, toErrorMessage } from '@/components/ui/error-banner';

type OrderDetailResponse = {
  id: number;
  order_number: string;
  status: string;
  user: {
    id: number;
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
  financial_summary: {
    loan_number: string | null;
    principal: number;
    profit: number;
    total_repayable: number;
    outstanding: number;
    installment_count: number | null;
  };
  created_at: string;
};

type CommunicationsResponse = {
  order_id: number;
  items: {
    id: number;
    source_event: string;
    category: string;
    priority: string;
    title: string;
    body: string;
    status: string;
    is_read: boolean;
    created_at: string;
  }[];
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
  // Only a genuine 404 means "this order doesn't exist" -- any other
  // failure (network error, 5xx, auth) should surface as a real error
  // instead of being silently repainted as a misleading "not found" state.
  const response = await adminApiServer
    .get<OrderDetailResponse | { error: string }>(`/admin/orders/${id}`)
    .catch((err) => {
      if (err instanceof GatewayRequestError && err.status === 404) return null;
      throw err;
    });

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

  // Unlike the not-found case above, this is a secondary panel: a failure
  // here shouldn't take down the whole order detail page, but it also
  // shouldn't be silently repainted as "no communications" -- that's
  // indistinguishable from a genuinely empty history. Surface it inline.
  let communications: CommunicationsResponse = { order_id: response.id, items: [] };
  let communicationsError: string | null = null;
  try {
    communications = await adminApiServer.get<CommunicationsResponse>(`/admin/orders/${id}/communications`);
  } catch (err) {
    communicationsError = toErrorMessage(err, 'Failed to load communication log.');
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
            <div>Status: {response.status.replace(/_/g, ' ')}</div>
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
          <p className="mt-2 text-xl font-semibold text-white">{response.user.phone}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Package2 className="h-4 w-4 text-emerald-400" />
            Product
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{response.product.name || 'Unspecified'}</p>
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
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Loan</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{response.financial_summary.loan_number ?? 'Not yet financed'}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Installments</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{response.financial_summary.installment_count ?? '—'}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Outstanding</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{formatAmount(response.financial_summary.outstanding)}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Created</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{formatDate(response.created_at)}</dd>
            </div>
          </dl>
        </div>

        <div className="glass-panel rounded-3xl p-6">
          <h2 className="text-lg font-semibold text-white">Customer snapshot</h2>
          <p className="mt-4 text-sm leading-6 text-slate-400">{response.user.phone}</p>
          <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-300">
            Product price on record: {formatAmount(response.product.price)}
          </div>
        </div>
      </div>

      <div className="glass-panel rounded-3xl p-6">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-5 w-5 text-blue-400" />
          <h2 className="text-lg font-semibold text-white">Communication log</h2>
        </div>
        <p className="mt-1 text-sm text-slate-400">Notifications sent to the customer regarding this order.</p>
        {communicationsError ? (
          <ErrorBanner message={communicationsError} className="mt-4" />
        ) : communications.items.length > 0 ? (
          <div className="mt-4 space-y-2">
            {communications.items.map((c) => (
              <div key={c.id} className="rounded-xl bg-white/5 px-4 py-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-white">{c.title}</span>
                  <span className="text-xs text-slate-500">{formatDate(c.created_at)}</span>
                </div>
                <p className="mt-1 text-slate-400">{c.body}</p>
                <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
                  <span className="rounded-full bg-white/10 px-2 py-0.5">{c.category}</span>
                  <span>{c.status}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-sm text-slate-500">No communications logged for this order yet.</p>
        )}
      </div>
    </section>
  );
}
