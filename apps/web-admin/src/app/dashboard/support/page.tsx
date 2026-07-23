"use client";

import { CheckCircle, MessageSquare, Plus, Smile, UserPlus, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable } from "@/components/admin/data-table";
import { ErrorBanner, toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface Ticket {
  id: number;
  ticket_number?: string;
  user_id: number;
  subject: string;
  status: string;
  assigned_to: number | null;
  created_at: string;
  updated_at: string;
}

interface TicketListResponse {
  items: Ticket[];
  pagination: { page: number; limit: number; total: number };
}

interface TicketDetail extends Ticket {
  category: string;
  priority: string;
  sla_deadline: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  satisfaction_score: number | null;
  messages: {
    id: number;
    sender_type: string;
    sender_id: number | null;
    message_text: string;
    is_internal_note: boolean;
    created_at: string;
  }[];
}

interface SupportDashboard {
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  sla_breached: number;
  avg_resolution_hours_30d: number | null;
}

interface CsatSummary {
  response_count: number;
  avg_score: number;
  csat_pct: number | null;
}

interface CannedResponse {
  id: number;
  title: string;
  body: string;
  category: string | null;
  usage_count: number;
  is_active: boolean;
}

const statusStyles: Record<string, string> = {
  open: "bg-blue-500/20 text-blue-400 border border-blue-500/30",
  in_progress: "bg-amber-500/20 text-amber-400 border border-amber-500/30",
  waiting_user: "bg-purple-500/20 text-purple-400 border border-purple-500/30",
  escalated: "bg-rose-500/20 text-rose-400 border border-rose-500/30",
  resolved: "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30",
  closed: "bg-slate-500/20 text-slate-400 border border-slate-500/30",
};

const TABS = [
  { key: "tickets", label: "Support Tickets", id: "AD-16" },
  { key: "canned", label: "Canned Responses", id: "" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function SupportPage() {
  const [tab, setTab] = useState<TabKey>("tickets");
  const [dashboard, setDashboard] = useState<SupportDashboard | null>(null);
  const [csat, setCsat] = useState<CsatSummary | null>(null);
  const [widgetsError, setWidgetsError] = useState<string | null>(null);

  const fetchWidgets = useCallback(async () => {
    try {
      const [d, c] = await Promise.all([
        adminApi.get<SupportDashboard>("/admin/support/dashboard"),
        adminApi.get<CsatSummary>("/admin/support/csat?days=90"),
      ]);
      setDashboard(d);
      setCsat(c);
      setWidgetsError(null);
    } catch (err) {
      setWidgetsError(toErrorMessage(err, "Failed to load support dashboard."));
    }
  }, []);

  useEffect(() => {
    fetchWidgets();
  }, [tab, fetchWidgets]);

  const openCount = dashboard?.by_status.open ?? 0;
  const inProgressCount = dashboard?.by_status.in_progress ?? 0;
  const resolvedCount = (dashboard?.by_status.resolved ?? 0) + (dashboard?.by_status.closed ?? 0);

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-16 / AD-17</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Support &amp; escalations</h2>
      </div>

      {widgetsError && <ErrorBanner message={widgetsError} onRetry={fetchWidgets} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <MessageSquare className="h-4 w-4 text-blue-500" />
            Open
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{openCount}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <MessageSquare className="h-4 w-4 text-amber-500" />
            In Progress
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{inProgressCount}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <MessageSquare className="h-4 w-4 text-emerald-500" />
            Resolved / Closed
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{resolvedCount}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <MessageSquare className="h-4 w-4 text-rose-500" />
            SLA Breached
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{dashboard?.sla_breached ?? 0}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Smile className="h-4 w-4 text-purple-500" />
            CSAT (90d)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">
            {csat?.csat_pct != null ? `${csat.csat_pct}%` : "—"}
          </p>
          <p className="text-xs text-slate-500">{csat?.response_count ?? 0} responses</p>
        </div>
      </div>

      <div className="flex gap-2 border-b border-white/10">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium transition ${
              tab === t.key ? "border-b-2 border-amber-400 text-white" : "text-slate-400 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "tickets" && <TicketsTab />}
      {tab === "canned" && <CannedResponsesTab />}
    </section>
  );
}

function TicketsTab() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [selected, setSelected] = useState<TicketDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchTickets = useCallback(async () => {
    setLoading(true);
    try {
      const query = statusFilter ? `?status=${statusFilter}&limit=100` : "?limit=100";
      const response = await adminApi.get<TicketListResponse>(`/admin/support/tickets${query}`);
      setTickets(response.items);
      setTotal(response.pagination.total);
      setError(null);
    } catch (err) {
      setTickets([]);
      setError(toErrorMessage(err, "Failed to load support tickets."));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchTickets();
  }, [fetchTickets]);

  const openDetail = async (id: number) => {
    const detail = await adminApi.get<TicketDetail>(`/admin/support/tickets/${id}`);
    setSelected(detail);
  };

  const handleAssignToMe = async (ticketId: number) => {
    setBusyId(ticketId);
    try {
      const meRaw = await fetch("/api/gateway/admin/auth/me").then((r) => (r.ok ? r.json() : null));
      const adminId = meRaw?.admin_id ?? meRaw?.id;
      if (adminId) {
        await adminApi.post(`/admin/support/tickets/${ticketId}/assign`, { admin_id: adminId });
      }
      await fetchTickets();
      if (selected?.id === ticketId) await openDetail(ticketId);
    } finally {
      setBusyId(null);
    }
  };

  const handleResolve = async (ticketId: number) => {
    const note = prompt("Resolution note (min 5 characters):");
    if (!note || note.trim().length < 5) return;
    setBusyId(ticketId);
    try {
      await adminApi.post(`/admin/support/tickets/${ticketId}/resolve`, { resolution_note: note.trim() });
      await fetchTickets();
      if (selected?.id === ticketId) await openDetail(ticketId);
    } finally {
      setBusyId(null);
    }
  };

  const handleClose = async (ticketId: number) => {
    if (!confirm("Close this ticket?")) return;
    setBusyId(ticketId);
    try {
      await adminApi.post(`/admin/support/tickets/${ticketId}/close`, {});
      await fetchTickets();
      if (selected?.id === ticketId) setSelected(null);
    } finally {
      setBusyId(null);
    }
  };

  const columns = [
    { key: "id", label: "ID", render: (v: unknown) => <span className="font-mono text-sm text-white">#{String(v)}</span> },
    { key: "subject", label: "Subject", render: (v: unknown) => <span className="text-slate-300">{String(v)}</span> },
    { key: "user_id", label: "User", render: (v: unknown) => <span className="text-slate-400">#{String(v)}</span> },
    {
      key: "status",
      label: "Status",
      render: (status: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[String(status)] || "bg-slate-500/20 text-slate-400"}`}>
          {String(status).replace(/_/g, " ")}
        </span>
      ),
    },
    { key: "assigned_to", label: "Assigned", render: (v: unknown) => <span className="text-slate-400">{v ? `#${v}` : "Unassigned"}</span> },
    {
      key: "created_at",
      label: "Created",
      render: (v: unknown) => (
        <span className="text-slate-400">
          {new Date(String(v)).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" })}
        </span>
      ),
    },
    {
      key: "actions",
      label: "Actions",
      render: (_value: unknown, row: Ticket) => {
        const ticketId = Number(row.id);
        const disabled = busyId === ticketId || row.status === "closed";
        return (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => openDetail(ticketId)}
              className="rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold text-white hover:bg-white/20"
            >
              View
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => handleAssignToMe(ticketId)}
              className="rounded-lg p-2 text-slate-400 transition hover:bg-blue-500/10 hover:text-blue-400 disabled:opacity-30"
              title="Assign to me"
            >
              <UserPlus className="h-4 w-4" />
            </button>
            <button
              type="button"
              disabled={disabled || row.status === "resolved"}
              onClick={() => handleResolve(ticketId)}
              className="rounded-lg p-2 text-slate-400 transition hover:bg-emerald-500/10 hover:text-emerald-400 disabled:opacity-30"
              title="Resolve"
            >
              <CheckCircle className="h-4 w-4" />
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => handleClose(ticketId)}
              className="rounded-lg p-2 text-slate-400 transition hover:bg-rose-500/10 hover:text-rose-400 disabled:opacity-30"
              title="Close"
            >
              <XCircle className="h-4 w-4" />
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white outline-none focus:border-amber-400/60"
        >
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="in_progress">In progress</option>
          <option value="waiting_user">Waiting on user</option>
          <option value="escalated">Escalated</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>
      </div>

      <DataTable columns={columns} data={tickets} keyField="id" loading={loading} error={error} onRetry={fetchTickets} />
      <p className="text-sm text-slate-400">
        Showing <span className="font-semibold text-white">{tickets.length}</span> of{" "}
        <span className="font-semibold text-white">{total}</span> tickets
      </p>

      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setSelected(null)}>
          <div
            className="glass-panel max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-[2rem] p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500">{selected.ticket_number}</p>
                <h3 className="mt-1 text-lg font-semibold text-white">{selected.subject}</h3>
              </div>
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[selected.status] || ""}`}>
                {selected.status.replace(/_/g, " ")}
              </span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-slate-400 sm:grid-cols-3">
              <p>Category: <span className="text-white">{selected.category}</span></p>
              <p>Priority: <span className="text-white">{selected.priority}</span></p>
              <p>Assigned: <span className="text-white">{selected.assigned_to ? `#${selected.assigned_to}` : "Unassigned"}</span></p>
            </div>
            <div className="mt-4 space-y-2">
              <h4 className="text-sm font-semibold text-white">Conversation</h4>
              {selected.messages.length > 0 ? (
                selected.messages.map((m) => (
                  <div key={m.id} className="rounded-xl bg-white/5 px-4 py-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-white">
                        {m.sender_type === "agent" ? `Agent #${m.sender_id}` : m.sender_type === "user" ? "Customer" : m.sender_type}
                      </span>
                      <span className="text-xs text-slate-500">{new Date(m.created_at).toLocaleString()}</span>
                    </div>
                    <p className="mt-1 text-slate-300">{m.message_text}</p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-500">No messages yet.</p>
              )}
            </div>
            <div className="mt-4 flex items-center gap-3">
              <button
                type="button"
                onClick={() => handleAssignToMe(selected.id)}
                className="rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
              >
                Assign to me
              </button>
              <button
                type="button"
                onClick={() => handleResolve(selected.id)}
                className="rounded-full bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400"
              >
                Resolve
              </button>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="ml-auto rounded-full px-4 py-2 text-sm font-semibold text-slate-400 hover:text-white"
              >
                Close panel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CannedResponsesTab() {
  const [responses, setResponses] = useState<CannedResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [category, setCategory] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchResponses = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.get<{ items: CannedResponse[] }>("/admin/support/canned-responses");
      setResponses(r.items);
      setError(null);
    } catch (err) {
      setResponses([]);
      setError(toErrorMessage(err, "Failed to load canned responses."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchResponses();
  }, [fetchResponses]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await adminApi.post("/admin/support/canned-responses", { title, body, category: category || undefined });
      setTitle("");
      setBody("");
      setCategory("");
      setShowForm(false);
      await fetchResponses();
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeactivate = async (id: number) => {
    if (!confirm("Deactivate this canned response?")) return;
    await adminApi.delete(`/admin/support/canned-responses/${id}`);
    await fetchResponses();
  };

  const columns = [
    { key: "title", label: "Title", render: (v: unknown) => <span className="font-medium text-white">{String(v)}</span> },
    { key: "body", label: "Body", render: (v: unknown) => <span className="text-slate-400 line-clamp-2">{String(v)}</span> },
    { key: "category", label: "Category", render: (v: unknown) => <span className="text-slate-400">{v ? String(v) : "—"}</span> },
    { key: "usage_count", label: "Used", render: (v: unknown) => <span className="text-slate-300">{String(v)}</span> },
    {
      key: "id",
      label: "",
      render: (id: unknown) => (
        <button
          type="button"
          onClick={() => handleDeactivate(Number(id))}
          className="rounded-full px-3 py-1.5 text-xs font-semibold text-rose-400 hover:bg-rose-500/10"
        >
          Deactivate
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setShowForm((s) => !s)}
          className="flex items-center gap-2 rounded-full bg-amber-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-amber-300"
        >
          <Plus className="h-4 w-4" />
          New response
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="glass-panel space-y-4 rounded-[2rem] p-5">
          <div>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Title</label>
            <input
              required
              placeholder="e.g. Refund processing time"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-amber-400/60"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Body</label>
            <textarea
              required
              rows={3}
              placeholder="Response text sent to the customer"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-amber-400/60"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Category (optional)</label>
            <input
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="e.g. refund_request"
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-amber-400/60"
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={submitting}
              className="rounded-full bg-amber-400 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-amber-300 disabled:opacity-60"
            >
              {submitting ? "Saving..." : "Save response"}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className="rounded-full px-5 py-2.5 text-sm font-semibold text-slate-400 hover:text-white">
              Cancel
            </button>
          </div>
        </form>
      )}

      <DataTable columns={columns} data={responses} keyField="id" loading={loading} error={error} onRetry={fetchResponses} />
    </div>
  );
}
