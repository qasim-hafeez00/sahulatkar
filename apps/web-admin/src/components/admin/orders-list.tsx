'use client';

import { Package, Plus, Search, TrendingUp } from 'lucide-react';
import Link from 'next/link';
import React, { useCallback, useEffect, useState } from 'react';
import { DataTable, SortDirection } from '@/components/admin/data-table';
import { ErrorBanner, toErrorMessage } from '@/components/ui/error-banner';
import { adminApi } from '@/lib/api-client';

interface Order {
  id: number;
  order_number: string;
  user_phone: string;
  product_name: string;
  status: string;
  total_amount: number;
  down_payment: number;
  created_at: string;
}

interface OrdersResponse {
  orders: Order[];
  total: number;
  page: number;
  limit: number;
}

interface OrdersSummary {
  by_status: Record<string, number>;
  total_orders: number;
  active_orders: number;
  orders_today: number;
  avg_order_value: number;
  gmv: number;
}

const statusStyles: Record<string, string> = {
  url_submitted: 'bg-slate-500/20 text-slate-400 border border-slate-500/30',
  url_received: 'bg-slate-500/20 text-slate-400 border border-slate-500/30',
  extraction_failed: 'bg-red-500/20 text-red-400 border border-red-500/30',
  contracts_pending: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
  down_payment_pending: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  down_payment_received: 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30',
  vcn_issued: 'bg-purple-500/20 text-purple-400 border border-purple-500/30',
  delivery_pending: 'bg-purple-500/20 text-purple-400 border border-purple-500/30',
  in_transit: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  delivered: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  cancelled: 'bg-red-500/20 text-red-400 border border-red-500/30',
  refunded: 'bg-red-500/20 text-red-400 border border-red-500/30',
};

function formatPkr(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `PKR ${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `PKR ${(value / 1_000).toFixed(1)}K`;
  return `PKR ${value.toFixed(0)}`;
}

export function OrdersList() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(50);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [sortKey, setSortKey] = useState<string | undefined>(undefined);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);
  const [summary, setSummary] = useState<OrdersSummary | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        limit: String(limit),
      });
      if (search) params.append('q', search);
      if (sortKey) {
        params.append('sort_by', sortKey);
        if (sortDirection) params.append('sort_dir', sortDirection);
      }

      const response = await adminApi.get<OrdersResponse>(
        `/admin/orders?${params.toString()}`
      );

      setOrders(response.orders);
      setTotal(response.total);
      setError(null);
    } catch (error) {
      console.error('Failed to fetch orders:', error);
      setError(toErrorMessage(error, 'Failed to load orders.'));
    } finally {
      setLoading(false);
    }
  }, [page, limit, search, sortKey, sortDirection]);

  const fetchSummary = useCallback(async () => {
    try {
      const s = await adminApi.get<OrdersSummary>('/admin/orders/summary');
      setSummary(s);
      setSummaryError(null);
    } catch (error) {
      setSummary(null);
      setSummaryError(toErrorMessage(error, 'Failed to load order stats.'));
    }
  }, []);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  const handleSort = (key: string, direction: SortDirection) => {
    setSortKey(key);
    setSortDirection(direction);
    setPage(1);
  };

  const columns = [
    {
      key: 'order_number',
      label: 'Order #',
      sortable: true,
      render: (orderNumber: unknown, row: Order) => (
        <Link href={`/dashboard/orders/${row.id}`} className="font-semibold text-white hover:text-blue-300">
          {String(orderNumber)}
        </Link>
      ),
    },
    {
      key: 'user_phone',
      label: 'Customer',
      sortable: false,
      render: (phone: unknown) => <span className="text-slate-300">{String(phone || '—')}</span>,
    },
    {
      key: 'product_name',
      label: 'Product',
      sortable: false,
      render: (name: unknown) => <span className="text-slate-400">{String(name || '—')}</span>,
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (status: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[String(status)] || 'bg-slate-500/20 text-slate-400'}`}>
          {String(status).replace(/_/g, ' ')}
        </span>
      ),
    },
    {
      key: 'total_amount',
      label: 'Total',
      sortable: true,
      render: (amount: unknown) => <span className="font-semibold text-white">PKR {Number(amount).toLocaleString()}</span>,
    },
    {
      key: 'down_payment',
      label: 'Down Payment',
      sortable: false,
      render: (amount: unknown) => <span className="text-slate-400">PKR {Number(amount).toLocaleString()}</span>,
    },
    {
      key: 'created_at',
      label: 'Created',
      sortable: true,
      render: (date: unknown) => {
        const formatted = new Date(String(date)).toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
          year: '2-digit',
        });
        return <span className="text-slate-400">{formatted}</span>;
      },
    },
  ];

  const totalPages = Math.ceil(total / limit);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-04 / AD-05</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Order management</h2>
        </div>
        <button
          type="button"
          onClick={() => setShowCreateForm((s) => !s)}
          className="flex items-center gap-2 rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700"
        >
          <Plus className="h-4 w-4" />
          Create Order
        </button>
      </div>

      {summaryError && <ErrorBanner message={summaryError} onRetry={fetchSummary} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Package className="h-4 w-4 text-blue-500" />
            Active Orders
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{summary?.active_orders ?? '—'}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Package className="h-4 w-4 text-emerald-500" />
            Orders Today
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{summary?.orders_today ?? '—'}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <TrendingUp className="h-4 w-4 text-amber-500" />
            Avg Order Value
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{summary ? formatPkr(summary.avg_order_value) : '—'}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <TrendingUp className="h-4 w-4 text-purple-500" />
            GMV (active)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{summary ? formatPkr(summary.gmv) : '—'}</p>
        </div>
      </div>

      {showCreateForm && (
        <CreateOrderForm
          onCreated={() => {
            setShowCreateForm(false);
            fetchOrders();
            fetchSummary();
          }}
          onCancel={() => setShowCreateForm(false)}
        />
      )}

      <div className="glass-panel rounded-2xl p-4">
        <div className="flex items-center gap-3 rounded-xl bg-slate-950/50 px-4 py-2">
          <Search className="h-4 w-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search by order number or customer..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="flex-1 border-0 bg-transparent text-sm text-white placeholder-slate-500 outline-none"
          />
        </div>
      </div>

      <DataTable
        columns={columns}
        data={orders}
        keyField="id"
        onSort={handleSort}
        sortKey={sortKey}
        sortDirection={sortDirection}
        loading={loading}
        error={error}
        onRetry={fetchOrders}
      />

      <div className="flex items-center justify-between rounded-xl bg-slate-950/50 p-4">
        <span className="text-sm text-slate-400">
          Showing <span className="font-semibold text-white">{orders.length}</span> of{' '}
          <span className="font-semibold text-white">{total}</span> orders
        </span>
        <div className="flex items-center gap-2">
          <button
            disabled={page === 1}
            onClick={() => setPage(Math.max(1, page - 1))}
            className="rounded px-3 py-1 text-sm disabled:opacity-50 hover:bg-white/10"
          >
            Previous
          </button>
          <span className="text-sm text-slate-400">
            Page <span className="font-semibold text-white">{page}</span> of{' '}
            <span className="font-semibold text-white">{totalPages}</span>
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            className="rounded px-3 py-1 text-sm disabled:opacity-50 hover:bg-white/10"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

function CreateOrderForm({ onCreated, onCancel }: { onCreated: () => void; onCancel: () => void }) {
  const [userId, setUserId] = useState('');
  const [productName, setProductName] = useState('');
  const [totalAmount, setTotalAmount] = useState('');
  const [downPaymentPct, setDownPaymentPct] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<{ id: number; order_number: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const created = await adminApi.post<{ id: number; order_number: string }>('/admin/orders', {
        user_id: Number(userId),
        product_name: productName,
        total_amount: Number(totalAmount),
        down_payment_pct: downPaymentPct ? Number(downPaymentPct) : undefined,
        notes,
      });
      setResult(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create order');
    } finally {
      setSubmitting(false);
    }
  };

  if (result) {
    return (
      <div className="glass-panel space-y-3 rounded-[2rem] p-5">
        <h3 className="text-lg font-semibold text-white">Order created</h3>
        <p className="text-sm text-slate-300">
          Order <span className="font-mono text-white">{result.order_number}</span> (#{result.id}) created and moved to
          contracts-pending.
        </p>
        <button
          type="button"
          onClick={onCreated}
          className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Done
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="glass-panel space-y-4 rounded-[2rem] p-5">
      <h3 className="text-lg font-semibold text-white">Create order (CS-assisted / phone order)</h3>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">User ID</label>
          <input
            required
            type="number"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-blue-400/60"
            placeholder="e.g. 123"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Total amount (PKR)</label>
          <input
            required
            type="number"
            min={1}
            value={totalAmount}
            onChange={(e) => setTotalAmount(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-blue-400/60"
            placeholder="e.g. 85000"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Product description</label>
          <input
            required
            value={productName}
            onChange={(e) => setProductName(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-blue-400/60"
            placeholder="e.g. Samsung Galaxy A54, 128GB, Black"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Down payment % (optional)</label>
          <input
            type="number"
            min={0}
            max={100}
            value={downPaymentPct}
            onChange={(e) => setDownPaymentPct(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-blue-400/60"
            placeholder="Defaults to system parameter"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Notes (why is this being created manually?)</label>
          <input
            required
            minLength={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-blue-400/60"
            placeholder="e.g. Customer called support line to place order"
          />
        </div>
      </div>
      {error && <p className="text-sm text-rose-400">{error}</p>}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-60"
        >
          {submitting ? 'Creating...' : 'Create order'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-full px-5 py-2.5 text-sm font-semibold text-slate-400 hover:text-white"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
