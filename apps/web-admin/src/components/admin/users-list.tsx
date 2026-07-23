'use client';

import { Plus, Search } from 'lucide-react';
import Link from 'next/link';
import React, { useCallback, useEffect, useState } from 'react';
import { DataTable, SortDirection } from '@/components/admin/data-table';
import { toErrorMessage } from '@/components/ui/error-banner';
import { adminApi } from '@/lib/api-client';

interface User {
  id: number;
  phone: string;
  status: string;
  created_at: string;
  failed_login_attempts: number;
  locked_until: string | null;
  credit_limit: number;
  available_credit: number;
  risk_band: string | null;
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

const statusStyles: Record<string, string> = {
  active: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  suspended: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  blocked: 'bg-red-500/20 text-red-400 border border-red-500/30',
  pending_kyc: 'bg-slate-500/20 text-slate-400 border border-slate-500/30',
  closed: 'bg-slate-700/40 text-slate-500 border border-slate-600/30',
};

const riskBandStyles: Record<string, string> = {
  low: 'bg-emerald-500/20 text-emerald-400',
  medium: 'bg-amber-500/20 text-amber-400',
  high: 'bg-rose-500/20 text-rose-400',
};

export function UsersList() {
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(50);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [sortKey, setSortKey] = useState<string | undefined>(undefined);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [showAddForm, setShowAddForm] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        limit: String(limit),
      });
      if (search) params.append('search', search);
      if (statusFilter) params.append('status', statusFilter);
      if (sortKey) {
        params.append('sort_by', sortKey);
        if (sortDirection) params.append('sort_dir', sortDirection);
      }

      const response = await adminApi.get<UsersResponse>(
        `/admin/users?${params.toString()}`
      );

      setUsers(response.items);
      setTotal(response.pagination.total);
      setSelected(new Set());
      setError(null);
    } catch (error) {
      console.error('Failed to fetch users:', error);
      setError(toErrorMessage(error, 'Failed to load users.'));
    } finally {
      setLoading(false);
    }
  }, [page, limit, search, statusFilter, sortKey, sortDirection]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleSort = (key: string, direction: SortDirection) => {
    setSortKey(key);
    setSortDirection(direction);
    setPage(1);
  };

  const toggleSelected = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelected((prev) => (prev.size === users.length ? new Set() : new Set(users.map((u) => u.id))));
  };

  const runBulkAction = async (action: 'suspend' | 'activate' | 'block') => {
    if (selected.size === 0) return;
    const reason = prompt(`Reason for bulk ${action}:`);
    if (!reason || reason.trim().length < 3) return;
    setBulkBusy(true);
    try {
      await adminApi.post('/admin/users/bulk', {
        user_ids: Array.from(selected),
        action,
        reason: reason.trim(),
      });
      await fetchUsers();
    } finally {
      setBulkBusy(false);
    }
  };

  const columns = [
    {
      key: 'id',
      label: '',
      className: 'w-10',
      render: (id: unknown) => (
        <input
          type="checkbox"
          aria-label={`Select user ${String(id)}`}
          checked={selected.has(Number(id))}
          onChange={() => toggleSelected(Number(id))}
          className="h-4 w-4 rounded border-white/20 bg-white/5"
        />
      ),
    },
    {
      key: 'phone',
      label: 'Phone',
      sortable: true,
      render: (phone: unknown, row: User) => (
        <Link href={`/dashboard/users/${row.id}`} className="font-medium text-white hover:text-blue-300">
          {String(phone)}
        </Link>
      ),
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
      key: 'risk_band',
      label: 'Risk Band',
      render: (v: unknown) =>
        v ? (
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${riskBandStyles[String(v)] || 'bg-slate-500/20 text-slate-400'}`}>
            {String(v)}
          </span>
        ) : (
          <span className="text-slate-500">—</span>
        ),
    },
    {
      key: 'credit_limit',
      label: 'Credit Limit',
      sortable: true,
      render: (v: unknown) => <span className="text-white">PKR {Number(v).toLocaleString()}</span>,
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
        <button
          type="button"
          onClick={() => setShowAddForm((s) => !s)}
          className="flex items-center gap-2 rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700"
        >
          <Plus className="h-4 w-4" />
          Add User
        </button>
      </div>

      {showAddForm && <AddUserForm onCreated={() => { setShowAddForm(false); fetchUsers(); }} onCancel={() => setShowAddForm(false)} />}

      <div className="glass-panel flex flex-wrap items-center gap-3 rounded-2xl p-4">
        <div className="flex flex-1 min-w-[200px] items-center gap-3 rounded-xl bg-slate-950/50 px-4 py-2">
          <Search className="h-4 w-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search by phone or ID..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="flex-1 border-0 bg-transparent text-sm text-white placeholder-slate-500 outline-none"
          />
        </div>
        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white outline-none focus:border-amber-400/60"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
          <option value="blocked">Blocked</option>
          <option value="pending_kyc">Pending KYC</option>
          <option value="closed">Closed</option>
        </select>
      </div>

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl bg-blue-500/10 px-4 py-3 text-sm">
          <span className="font-semibold text-white">{selected.size} selected</span>
          <button
            type="button"
            disabled={bulkBusy}
            onClick={() => runBulkAction('activate')}
            className="rounded-full bg-emerald-500/80 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            Activate
          </button>
          <button
            type="button"
            disabled={bulkBusy}
            onClick={() => runBulkAction('suspend')}
            className="rounded-full bg-amber-500/80 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-500 disabled:opacity-50"
          >
            Suspend
          </button>
          <button
            type="button"
            disabled={bulkBusy}
            onClick={() => runBulkAction('block')}
            className="rounded-full bg-rose-500/80 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-50"
          >
            Block
          </button>
          <button
            type="button"
            onClick={toggleSelectAll}
            className="ml-auto text-xs font-semibold text-slate-400 hover:text-white"
          >
            {selected.size === users.length ? 'Clear selection' : 'Select all on page'}
          </button>
        </div>
      )}

      <DataTable
        columns={columns}
        data={users}
        keyField="id"
        onSort={handleSort}
        sortKey={sortKey}
        sortDirection={sortDirection}
        loading={loading}
        error={error}
        onRetry={fetchUsers}
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

function AddUserForm({ onCreated, onCancel }: { onCreated: () => void; onCancel: () => void }) {
  const [phone, setPhone] = useState('+92');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [initialStatus, setInitialStatus] = useState<'pending_kyc' | 'active'>('pending_kyc');
  const [initialCreditLimit, setInitialCreditLimit] = useState('0');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<{ id: number; phone: string; temp_password: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const created = await adminApi.post<{ id: number; phone: string; status: string; temp_password: string }>(
        '/admin/users',
        {
          phone,
          first_name: firstName || undefined,
          last_name: lastName || undefined,
          initial_status: initialStatus,
          initial_credit_limit: Number(initialCreditLimit) || 0,
        }
      );
      setResult(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create user');
    } finally {
      setSubmitting(false);
    }
  };

  if (result) {
    return (
      <div className="glass-panel space-y-3 rounded-[2rem] p-5">
        <h3 className="text-lg font-semibold text-white">User created</h3>
        <p className="text-sm text-slate-300">
          Account <span className="font-mono text-white">{result.phone}</span> created (ID #{result.id}).
        </p>
        <p className="text-sm text-slate-300">
          Temporary password (share with the customer, they should reset it on first login):
        </p>
        <p className="rounded-lg bg-black/30 px-4 py-2 font-mono text-amber-300">{result.temp_password}</p>
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
      <h3 className="text-lg font-semibold text-white">Add user (CS-assisted signup)</h3>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Phone (+92XXXXXXXXXX)</label>
          <input
            required
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            pattern="^\+92[0-9]{10}$"
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-blue-400/60"
            placeholder="+923001234567"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Initial status</label>
          <select
            aria-label="Initial account status"
            value={initialStatus}
            onChange={(e) => setInitialStatus(e.target.value as 'pending_kyc' | 'active')}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-blue-400/60"
          >
            <option value="pending_kyc">Pending KYC</option>
            <option value="active">Active (pre-vetted)</option>
          </select>
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">First name</label>
          <input
            aria-label="First name"
            placeholder="First name"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-blue-400/60"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Last name</label>
          <input
            aria-label="Last name"
            placeholder="Last name"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-blue-400/60"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Initial credit limit (PKR)</label>
          <input
            aria-label="Initial credit limit (PKR)"
            type="number"
            min={0}
            value={initialCreditLimit}
            onChange={(e) => setInitialCreditLimit(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-blue-400/60"
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
          {submitting ? 'Creating...' : 'Create user'}
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
