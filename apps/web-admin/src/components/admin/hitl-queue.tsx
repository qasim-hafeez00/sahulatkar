'use client';

import { AlertCircle, CheckCircle, Clock } from 'lucide-react';
import Link from 'next/link';
import React, { useCallback, useEffect, useState } from 'react';
import { DataTable, SortDirection } from '@/components/admin/data-table';
import { adminApi } from '@/lib/api-client';

interface HITLCase {
  id: number;
  case_id: string;
  case_type: string;
  related_order: number;
  user_email: string;
  priority: string;
  status: string;
  assigned_to: string | null;
  created_at: string;
  updated_at: string;
  resolution_notes: string | null;
}

interface HITLResponse {
  items: HITLCase[];
}

const priorityStyles: Record<string, string> = {
  low: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
  medium: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  high: 'bg-red-500/20 text-red-400 border border-red-500/30',
  critical: 'bg-red-600/30 text-red-300 border border-red-600/50',
};

const statusStyles: Record<string, string> = {
  open: 'bg-slate-500/20 text-slate-400 border border-slate-500/30',
  in_progress: 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30',
  waiting: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  resolved: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  closed: 'bg-slate-600/20 text-slate-400 border border-slate-600/30',
};

export function HITLQueue() {
  const [cases, setCases] = useState<HITLCase[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(50);
  const [loading, setLoading] = useState(false);
  const [sortKey, setSortKey] = useState<string | undefined>(undefined);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);

  const fetchCases = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (sortKey) {
        params.append('sort_by', sortKey);
        if (sortDirection) params.append('sort_dir', sortDirection);
      }

      const response = await adminApi.get<HITLResponse>(
        `/admin/hitl/queue?${params.toString()}`
      );

      setCases(response.items);
      setTotal(response.items.length);
    } catch (error) {
      console.error('Failed to fetch HITL cases:', error);
    } finally {
      setLoading(false);
    }
  }, [sortKey, sortDirection]);

  useEffect(() => {
    fetchCases();
  }, [fetchCases]);

  const handleSort = (key: string, direction: SortDirection) => {
    setSortKey(key);
    setSortDirection(direction);
    setPage(1);
  };

  const columns = [
    {
      key: 'case_id',
      label: 'Case ID',
      sortable: true,
      render: (caseId: unknown, row: HITLCase) => (
        <Link href={`/dashboard/hitl/${row.id}`} className="font-mono text-sm font-semibold text-white hover:text-blue-300">
          {String(caseId)}
        </Link>
      ),
    },
    {
      key: 'case_type',
      label: 'Type',
      sortable: true,
      render: (type: unknown) => <span className="text-slate-400">{String(type).replace(/_/g, ' ')}</span>,
    },
    {
      key: 'user_email',
      label: 'User',
      sortable: false,
      render: (email: unknown) => <span className="text-slate-400">{String(email)}</span>,
    },
    {
      key: 'priority',
      label: 'Priority',
      sortable: true,
      render: (priority: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${priorityStyles[String(priority)] || 'bg-slate-500/20 text-slate-400'}`}>
          {String(priority)}
        </span>
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
      key: 'assigned_to',
      label: 'Assigned To',
      sortable: false,
      render: (assignee: unknown) => <span className="text-slate-400">{String(assignee || '—')}</span>,
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
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-08 / AD-09</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">HITL queue</h2>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <AlertCircle className="h-4 w-4 text-amber-500" />
            Pending Resolution
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{total}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Clock className="h-4 w-4 text-blue-500" />
            In Progress
          </div>
          <p className="mt-2 text-2xl font-bold text-white">—</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <CheckCircle className="h-4 w-4 text-emerald-500" />
            Resolved Today
          </div>
          <p className="mt-2 text-2xl font-bold text-white">—</p>
        </div>
      </div>

      <DataTable
        columns={columns}
        data={cases}
        keyField="id"
        onSort={handleSort}
        sortKey={sortKey}
        sortDirection={sortDirection}
        loading={loading}
      />

      <div className="flex items-center justify-between rounded-xl bg-slate-950/50 p-4">
        <span className="text-sm text-slate-400">
          Showing <span className="font-semibold text-white">{cases.length}</span> of{' '}
          <span className="font-semibold text-white">{total}</span> cases
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
