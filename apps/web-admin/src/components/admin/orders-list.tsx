'use client';

import { Search } from 'lucide-react';
import Link from 'next/link';
import React, { useCallback, useEffect, useState } from 'react';
import { DataTable, SortDirection } from '@/components/admin/data-table';
import { adminApi } from '@/lib/api-client';

interface Order {
  id: number;
  order_number: string;
  user_email: string;
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

const statusStyles: Record<string, string> = {
  PENDING: 'bg-slate-500/20 text-slate-400 border border-slate-500/30',
  APPROVED: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
  DOWN_PAYMENT_PENDING: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  DOWN_PAYMENT_RECEIVED: 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30',
  FINANCED: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  DELIVERY_PENDING: 'bg-purple-500/20 text-purple-400 border border-purple-500/30',
  IN_TRANSIT: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  DELIVERED: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  CANCELLED: 'bg-red-500/20 text-red-400 border border-red-500/30',
};

export function OrdersList() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(50);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [sortKey, setSortKey] = useState<string | undefined>(undefined);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);

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
    } catch (error) {
      console.error('Failed to fetch orders:', error);
    } finally {
      setLoading(false);
    }
  }, [page, limit, search, sortKey, sortDirection]);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

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
      key: 'user_email',
      label: 'Customer',
      sortable: true,
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
      </div>

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
