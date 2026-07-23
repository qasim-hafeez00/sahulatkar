"use client";

import { CheckCircle, FileText, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable } from "@/components/admin/data-table";
import { ErrorBanner, toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface DocumentItem {
  id: number;
  user_id: number;
  user_phone: string | null;
  document_type: string;
  status: string;
  mime_type: string | null;
  expiry_date: string | null;
  created_at: string;
}

const statusStyles: Record<string, string> = {
  pending: "bg-amber-500/20 text-amber-400",
  verified: "bg-emerald-500/20 text-emerald-400",
  rejected: "bg-rose-500/20 text-rose-400",
};

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const query = statusFilter ? `?status_filter=${statusFilter}&limit=100` : "?limit=100";
      const r = await adminApi.get<{ items: DocumentItem[]; pagination: { total: number } }>(`/admin/documents${query}`);
      setDocuments(r.items);
      setTotal(r.pagination.total);
      setError(null);
    } catch (err) {
      setDocuments([]);
      setError(toErrorMessage(err, "Failed to load documents."));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const fetchSummary = useCallback(async () => {
    try {
      const r = await adminApi.get<{ by_status: Record<string, number> }>("/admin/documents/summary/counts");
      setSummary(r.by_status);
      setSummaryError(null);
    } catch (err) {
      setSummaryError(toErrorMessage(err, "Failed to load document counts."));
    }
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [documents.length, fetchSummary]);

  const handleDecision = async (id: number, decision: "verified" | "rejected") => {
    const notes = prompt(`Verification notes for ${decision}:`) ?? "";
    setBusyId(id);
    try {
      await adminApi.post(`/admin/documents/${id}/decision`, { decision, verification_notes: notes || undefined });
      await fetchDocuments();
    } finally {
      setBusyId(null);
    }
  };

  const columns = [
    { key: "id", label: "ID", render: (v: unknown) => <span className="font-mono text-sm text-white">#{String(v)}</span> },
    { key: "user_phone", label: "User", render: (v: unknown, row: DocumentItem) => <span className="text-slate-300">{v ? String(v) : `#${row.user_id}`}</span> },
    { key: "document_type", label: "Document Type", render: (v: unknown) => <span className="text-slate-300">{String(v).replace(/_/g, " ")}</span> },
    {
      key: "status",
      label: "Status",
      render: (v: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[String(v)] || "bg-slate-500/20 text-slate-400"}`}>
          {String(v)}
        </span>
      ),
    },
    {
      key: "created_at",
      label: "Uploaded",
      render: (v: unknown) => <span className="text-slate-400">{new Date(String(v)).toLocaleDateString()}</span>,
    },
    {
      key: "actions",
      label: "Actions",
      render: (_value: unknown, row: DocumentItem) => {
        const docId = Number(row.id);
        const disabled = busyId === docId || row.status !== "pending";
        return (
          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={disabled}
              onClick={() => handleDecision(docId, "verified")}
              className="rounded-lg p-2 text-slate-400 hover:bg-emerald-500/10 hover:text-emerald-400 disabled:opacity-30"
              title="Verify"
            >
              <CheckCircle className="h-4 w-4" />
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => handleDecision(docId, "rejected")}
              className="rounded-lg p-2 text-slate-400 hover:bg-rose-500/10 hover:text-rose-400 disabled:opacity-30"
              title="Reject"
            >
              <XCircle className="h-4 w-4" />
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-32</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Document management</h2>
      </div>

      {summaryError && <ErrorBanner message={summaryError} onRetry={fetchSummary} />}

      <div className="grid gap-4 sm:grid-cols-3">
        {["pending", "verified", "rejected"].map((s) => (
          <div key={s} className="glass-panel rounded-xl p-4">
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <FileText className="h-4 w-4 text-blue-500" />
              {s}
            </div>
            <p className="mt-2 text-2xl font-bold text-white">{summary[s] ?? 0}</p>
          </div>
        ))}
      </div>

      <div className="flex justify-end">
        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white outline-none focus:border-amber-400/60"
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="verified">Verified</option>
          <option value="rejected">Rejected</option>
        </select>
      </div>

      <DataTable columns={columns} data={documents} keyField="id" loading={loading} error={error} onRetry={fetchDocuments} />
      <p className="text-sm text-slate-400">
        Showing <span className="font-semibold text-white">{documents.length}</span> of{" "}
        <span className="font-semibold text-white">{total}</span> documents
      </p>
    </section>
  );
}
