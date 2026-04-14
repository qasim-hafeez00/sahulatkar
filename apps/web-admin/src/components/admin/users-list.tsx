'use client';

import { Search, Plus } from 'lucide-react';
import Link from 'next/link';
import React, { useCallback, useEffect, useState } from 'react';
import { DataTable, SortDirection } from '@/components/admin/data-table';
import { adminApi } from '@/lib/api-client';

interface User {
  id: number;
  email: string;
  phone: string;
  kyc_status: string;
  account_status: string;
  created_at: string;
  total_orders: number;
}

interface UsersResponse {
  items: User[];
  pagination: {
    page: number;
    limit: number;
    total: number;
  };
}

const kycStatusStyles: Record<string, string> = {
  verified: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  pending: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  rejected: 'bg-red-500/20 text-red-400 border border-red-500/30',
};

const accountStatusStyles: Record<string, string> = {
  active: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
  suspended: 'bg-red-500/20 text-red-400 border border-red-500/30',
  pending: 'bg-slate-500/20 text-slate-400 border border-slate-500/30',
};

export function UsersList() {
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(50);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [sortKey, setSortKey] = useState<string | undefined>(undefined);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        limit: String(limit),
      });
      if (search) params.append('search', search);
      if (sortKey) {
        params.append('sort_by', sortKey);
        if (sortDirection) params.append('sort_dir', sortDirection);
      }

      const response = await adminApi.get<UsersResponse>(
        `/admin/users?${params.toString()}`
      );

      setUsers(response.items);
      setTotal(response.pagination.total);
    } catch (error) {
      console.error('Failed to fetch users:', error);
    } finally {
      setLoading(false);
    }
  }, [page, limit, search, sortKey, sortDirection]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleSort = (key: string, direction: SortDirection) => {
    setSortKey(key);
    setSortDirection(direction);
    setPage(1);
  };

  const columns = [
    {
      key: 'email',
      label: 'Email',
      sortable: true,
      render: (email: unknown, row: User) => (
        <Link href={`/dashboard/users/${row.id}`} className="font-medium text-white hover:text-blue-300">
          {String(email)}
        </Link>
      ),
    },
    {
      key: 'phone',
      label: 'Phone',
      sortable: false,
      render: (phone: unknown) => <span className="text-slate-400">{String(phone || '—')}</span>,
    },
    {
      key: 'kyc_status',
      label: 'KYC Status',
      sortable: true,
      render: (status: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${kycStatusStyles[String(status)] || 'bg-slate-500/20 text-slate-400'}`}>
          {String(status)}
        </span>
      ),
    },
    {
      key: 'account_status',
      label: 'Account',
      sortable: true,
      render: (status: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${accountStatusStyles[String(status)] || 'bg-slate-500/20 text-slate-400'}`}>
          {String(status)}
        </span>
      ),
    },
    {
      key: 'total_orders',
      label: 'Orders',
      sortable: true,
      render: (count: unknown) => <span className="font-semibold text-white">{String(count)}</span>,
    },
    {
      key: 'created_at',
      label: 'Joined',
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
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-02 / AD-03</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">User management</h2>
        </div>
        <button className="flex items-center gap-2 rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700">
          <Plus className="h-4 w-4" />
          Add User
        </button>
      </div>

      <div className="glass-panel rounded-2xl p-4">
        <div className="flex items-center gap-3 rounded-xl bg-slate-950/50 px-4 py-2">
          <Search className="h-4 w-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search by email or phone..."
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
        data={users}
        keyField="id"
        onSort={handleSort}
        sortKey={sortKey}
        sortDirection={sortDirection}
        loading={loading}
      />

      <div className="flex items-center justify-between rounded-xl bg-slate-950/50 p-4">
        <span className="text-sm text-slate-400">
          Showing <span className="font-semibold text-white">{users.length}</span> of{' '}
          <span className="font-semibold text-white">{total}</span> users
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
