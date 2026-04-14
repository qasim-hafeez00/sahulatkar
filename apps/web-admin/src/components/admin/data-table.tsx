'use client';

import { ChevronDown, ChevronUp, ChevronsUpDown } from 'lucide-react';
import React from 'react';

export type SortDirection = 'asc' | 'desc' | null;

export interface Column<T> {
  key: keyof T | string;
  label: string;
  sortable?: boolean;
  render?: (value: unknown, row: T) => React.ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyField: keyof T;
  onSort?: (key: string, direction: SortDirection) => void;
  sortKey?: string | null;
  sortDirection?: SortDirection;
  loading?: boolean;
}

export function DataTable<T>({
  columns,
  data,
  keyField,
  onSort,
  sortKey,
  sortDirection,
  loading,
}: DataTableProps<T>) {
  const handleHeaderClick = (column: Column<T>) => {
    if (!column.sortable || !onSort) return;

    let newDirection: SortDirection = 'asc';
    if (sortKey === column.key && sortDirection === 'asc') {
      newDirection = 'desc';
    } else if (sortKey === column.key && sortDirection === 'desc') {
      newDirection = null;
    }

    onSort(String(column.key), newDirection);
  };

  const getSortIcon = (column: Column<T>) => {
    if (!column.sortable) return null;
    if (sortKey !== column.key) {
      return <ChevronsUpDown className="h-4 w-4 text-slate-500" />;
    }
    if (sortDirection === 'asc') {
      return <ChevronUp className="h-4 w-4 text-white" />;
    }
    if (sortDirection === 'desc') {
      return <ChevronDown className="h-4 w-4 text-white" />;
    }
    return <ChevronsUpDown className="h-4 w-4 text-slate-500" />;
  };

  if (loading) {
    return (
      <div className="rounded-2xl border border-white/10 bg-slate-950/50 p-6">
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-slate-900/50" />
          ))}
        </div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-white/10 bg-slate-950/50 p-8 text-center">
        <p className="text-sm text-slate-400">No data available</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/50">
      <table className="w-full">
        <thead>
          <tr className="border-b border-white/10">
            {columns.map((column) => (
              <th
                key={String(column.key)}
                className={`px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.1em] text-slate-400 ${
                  column.sortable ? 'cursor-pointer hover:text-white' : ''
                } ${column.className || ''}`}
                onClick={() => handleHeaderClick(column)}
              >
                <div className="flex items-center gap-2">
                  {column.label}
                  {getSortIcon(column)}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, idx) => (
            <tr
              key={String(row[keyField])}
              className={`border-b border-white/5 transition-colors ${
                idx % 2 === 0 ? 'bg-transparent' : 'bg-white/[0.02]'
              } hover:bg-white/[0.05]`}
            >
              {columns.map((column) => (
                <td
                  key={String(column.key)}
                  className={`px-4 py-3 text-sm text-slate-300 ${column.className || ''}`}
                >
                  {column.render
                    ? column.render(row[column.key as keyof T], row)
                    : String(row[column.key as keyof T] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
