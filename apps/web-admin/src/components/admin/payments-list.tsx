'use client';

import { AlertTriangle, Clock, Search, TrendingUp, Wallet } from 'lucide-react';
import Link from 'next/link';
import React, { useCallback, useEffect, useState } from 'react';
import { DataTable, SortDirection } from '@/components/admin/data-table';
import { ErrorBanner, toErrorMessage } from '@/components/ui/error-banner';
import { adminApi } from '@/lib/api-client';

interface Payment {
  id: number;
  transaction_id: string;
  order_id: number;
  amount: number;
  currency: string;
  status: string;
  gateway: string;
  created_at: string;
  settled_at: string | null;
}

interface PaymentsResponse {
  payments: Payment[];
  total: number;
  page: number;
  limit: number;
}

interface CollectionsSummary {
  overdue_count: number;
  overdue_amount: number;
  pending_count: number;
  pending_amount: number;
  collected_today_amount: number;
  collected_mtd_amount: number;
  on_time_payment_rate: number | null;
}

interface AgingBucketsResponse {
  buckets: { bucket: string; count: number; amount: number }[];
}

const statusStyles: Record<string, string> = {
  pending: 'bg-slate-500/20 text-slate-400 border border-slate-500/30',
  initiated: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
  confirmed: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  failed: 'bg-red-500/20 text-red-400 border border-red-500/30',
  refunded: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
};

const bucketLabels: Record<string, string> = {
  current: 'Current',
  '1-30_days': '1-30 days',
  '31-60_days': '31-60 days',
  '61-90_days': '61-90 days',
  '90_plus_days': '90+ days',
};

function formatPkr(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `PKR ${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `PKR ${(value / 1_000).toFixed(1)}K`;
  return `PKR ${value.toFixed(0)}`;
}

export function PaymentsList() {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(50);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [sortKey, setSortKey] = useState<string | undefined>(undefined);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);
  const [summary, setSummary] = useState<CollectionsSummary | null>(null);
  const [aging, setAging] = useState<AgingBucketsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [widgetsError, setWidgetsError] = useState<string | null>(null);

  const fetchPayments = useCallback(async () => {
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

      const response = await adminApi.get<PaymentsResponse>(
        `/admin/payments?${params.toString()}`
      );

      setPayments(response.payments);
      setTotal(response.total);
      setError(null);
    } catch (error) {
      console.error('Failed to fetch payments:', error);
      setError(toErrorMessage(error, 'Failed to load payments.'));
    } finally {
      setLoading(false);
    }
  }, [page, limit, search, sortKey, sortDirection]);

  useEffect(() => {
    fetchPayments();
  }, [fetchPayments]);

  const fetchWidgets = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([
        adminApi.get<CollectionsSummary>('/admin/payments/collections-summary'),
        adminApi.get<AgingBucketsResponse>('/admin/payments/aging-buckets'),
      ]);
      setSummary(s);
      setAging(a);
      setWidgetsError(null);
    } catch (error) {
      setWidgetsError(toErrorMessage(error, 'Failed to load collections summary.'));
    }
  }, []);

  useEffect(() => {
    fetchWidgets();
  }, [fetchWidgets]);

  const handleSort = (key: string, direction: SortDirection) => {
    setSortKey(key);
    setSortDirection(direction);
    setPage(1);
  };

  const columns = [
    {
      key: 'transaction_id',
      label: 'Transaction ID',
      sortable: true,
      render: (txnId: unknown, row: Payment) => (
        <Link href={`/dashboard/payments/${row.id}`} className="font-mono text-sm text-white hover:text-blue-300">
          {txnId ? String(txnId) : `#${row.id}`}
        </Link>
      ),
    },
    {
      key: 'order_id',
      label: 'Order',
      sortable: true,
      render: (orderId: unknown) => <span className="text-slate-400">#{String(orderId)}</span>,
    },
    {
      key: 'amount',
      label: 'Amount',
      sortable: true,
      render: (_value: unknown, row: Payment) => (
        <span className="font-semibold text-white">
          {row.currency} {row.amount.toLocaleString()}
        </span>
      ),
    },
    {
      key: 'gateway',
      label: 'Gateway',
      sortable: true,
      render: (gateway: unknown) => (
        <span className="rounded-full bg-slate-500/20 px-2.5 py-1 text-xs text-slate-300">{String(gateway)}</span>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (status: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[String(status)] || 'bg-slate-500/20 text-slate-400'}`}>
          {String(status)}
        </span>
      ),
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
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-06 / AD-07</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Payment operations</h2>
        </div>
      </div>

      {widgetsError && <ErrorBanner message={widgetsError} onRetry={fetchWidgets} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <AlertTriangle className="h-4 w-4 text-rose-500" />
            Overdue
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{summary ? formatPkr(summary.overdue_amount) : '—'}</p>
          <p className="text-xs text-slate-500">{summary?.overdue_count ?? 0} installments</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Clock className="h-4 w-4 text-amber-500" />
            Pending
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{summary ? formatPkr(summary.pending_amount) : '—'}</p>
          <p className="text-xs text-slate-500">{summary?.pending_count ?? 0} installments</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Wallet className="h-4 w-4 text-emerald-500" />
            Collected (MTD)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{summary ? formatPkr(summary.collected_mtd_amount) : '—'}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <TrendingUp className="h-4 w-4 text-blue-500" />
            On-Time Rate
          </div>
          <p className="mt-2 text-2xl font-bold text-white">
            {summary?.on_time_payment_rate != null ? `${summary.on_time_payment_rate}%` : '—'}
          </p>
        </div>
      </div>

      <section className="glass-panel rounded-[2rem] p-5">
        <h3 className="text-lg font-semibold text-white">Aging buckets</h3>
        <p className="mt-1 text-sm text-slate-400">Outstanding installment balances by days overdue.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3 xl:grid-cols-5">
          {(aging?.buckets ?? []).map((b) => (
            <div key={b.bucket} className="rounded-xl bg-white/5 px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">{bucketLabels[b.bucket] ?? b.bucket}</p>
              <p className="mt-1 text-lg font-semibold text-white">{formatPkr(b.amount)}</p>
              <p className="text-xs text-slate-500">{b.count} installments</p>
            </div>
          ))}
        </div>
      </section>

      <div className="glass-panel rounded-2xl p-4">
        <div className="flex items-center gap-3 rounded-xl bg-slate-950/50 px-4 py-2">
          <Search className="h-4 w-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search by transaction ID..."
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
        data={payments}
        keyField="id"
        onSort={handleSort}
        sortKey={sortKey}
        sortDirection={sortDirection}
        loading={loading}
        error={error}
        onRetry={fetchPayments}
      />

      <div className="flex items-center justify-between rounded-xl bg-slate-950/50 p-4">
        <span className="text-sm text-slate-400">
          Showing <span className="font-semibold text-white">{payments.length}</span> of{' '}
          <span className="font-semibold text-white">{total}</span> payments
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
