"use client";

import { AlertTriangle, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable } from "@/components/admin/data-table";
import { ErrorBanner, toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface RiskDashboard {
  open_alerts_by_severity: Record<string, number>;
  review_queue_by_status: Record<string, number>;
  avg_resolution_hours_30d: number | null;
  blacklist_total: number;
  review_queue_overdue_sla: number;
}

interface FraudAlert {
  id: number;
  user_id: number | null;
  user_name: string | null;
  user_phone: string | null;
  order_id: number | null;
  alert_type: string;
  severity: "low" | "medium" | "high" | "critical";
  description: string | null;
  status: string;
  created_at: string;
}

interface UnderwritingItem {
  id: number;
  entity_type: string;
  entity_id: number;
  entity_name: string | null;
  entity_phone: string | null;
  queue_type: string;
  priority: number;
  assigned_to_email: string | null;
  status: string;
  sla_deadline: string | null;
  sla_breached: boolean;
  created_at: string;
}

interface UnderwritingDetail extends UnderwritingItem {
  notes: string | null;
  user_context: {
    name: string | null;
    phone: string;
    status: string;
    credit_limit: number;
    available_credit: number;
    risk_band: string | null;
  } | null;
  bank_statement_analysis: {
    period_start: string;
    period_end: string;
    avg_balance: number | null;
    income_estimate: number | null;
    expense_ratio: number | null;
    salary_detected: boolean;
    nsf_events: number;
  } | null;
}

interface BlacklistEntry {
  id: number;
  entry_type: "user" | "device" | "ip" | "phone";
  value: string;
  reason: string;
  user_id: number | null;
  created_at: string;
}

const severityStyles: Record<string, string> = {
  low: "bg-slate-500/20 text-slate-400 border border-slate-500/30",
  medium: "bg-amber-500/20 text-amber-400 border border-amber-500/30",
  high: "bg-orange-500/20 text-orange-400 border border-orange-500/30",
  critical: "bg-rose-500/20 text-rose-400 border border-rose-500/30",
};

const entryTypeStyles: Record<string, string> = {
  user: "bg-blue-500/20 text-blue-400 border border-blue-500/30",
  device: "bg-purple-500/20 text-purple-400 border border-purple-500/30",
  ip: "bg-amber-500/20 text-amber-400 border border-amber-500/30",
  phone: "bg-rose-500/20 text-rose-400 border border-rose-500/30",
};

const TABS = [
  { key: "alerts", label: "Risk Alerts", id: "AD-10" },
  { key: "underwriting", label: "Manual Underwriting", id: "AD-11" },
  { key: "blacklist", label: "Blacklist & Monitoring", id: "AD-12" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function RiskPage() {
  const [tab, setTab] = useState<TabKey>("alerts");
  const [dashboard, setDashboard] = useState<RiskDashboard | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);

  const fetchDashboard = useCallback(() => {
    adminApi
      .get<RiskDashboard>("/admin/risk/dashboard")
      .then((r) => {
        setDashboard(r);
        setDashboardError(null);
      })
      .catch((err) => setDashboardError(toErrorMessage(err, "Failed to load risk dashboard.")));
  }, []);

  useEffect(() => {
    fetchDashboard();
  }, [tab, fetchDashboard]);

  const openAlerts = dashboard
    ? Object.values(dashboard.open_alerts_by_severity).reduce((a, b) => a + b, 0)
    : 0;
  const pendingReview = dashboard
    ? (dashboard.review_queue_by_status.pending ?? 0) + (dashboard.review_queue_by_status.in_review ?? 0)
    : 0;

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-10 / AD-11 / AD-12</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Risk & fraud</h2>
      </div>

      {dashboardError && <ErrorBanner message={dashboardError} onRetry={fetchDashboard} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <ShieldAlert className="h-4 w-4 text-rose-500" />
            Open Fraud Alerts
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{openAlerts}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            Pending Underwriting Review
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{pendingReview}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <AlertTriangle className="h-4 w-4 text-orange-500" />
            SLA Overdue
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{dashboard?.review_queue_overdue_sla ?? 0}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <ShieldAlert className="h-4 w-4 text-blue-500" />
            Blacklisted Entries
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{dashboard?.blacklist_total ?? 0}</p>
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

      {tab === "alerts" && <FraudAlertsTab />}
      {tab === "underwriting" && <UnderwritingTab />}
      {tab === "blacklist" && <BlacklistTab />}
    </section>
  );
}

function FraudAlertsTab() {
  const [alerts, setAlerts] = useState<FraudAlert[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const query = statusFilter ? `?status_filter=${statusFilter}&limit=100` : "?limit=100";
      const response = await adminApi.get<{ items: FraudAlert[]; pagination: { total: number } }>(
        `/admin/risk/fraud-alerts${query}`
      );
      setAlerts(response.items);
      setTotal(response.pagination.total);
      setError(null);
    } catch (err) {
      setAlerts([]);
      setError(toErrorMessage(err, "Failed to load fraud alerts."));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const decide = async (id: number, status: string) => {
    const note = prompt(`Resolution note for "${status.replace(/_/g, " ")}" (optional):`) ?? "";
    setBusyId(id);
    try {
      await adminApi.post(`/admin/risk/fraud-alerts/${id}/decision`, {
        status,
        resolution_note: note || undefined,
      });
      await fetchAlerts();
    } finally {
      setBusyId(null);
    }
  };

  const columns = [
    {
      key: "severity",
      label: "Severity",
      render: (v: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${severityStyles[String(v)] || ""}`}>
          {String(v)}
        </span>
      ),
    },
    { key: "alert_type", label: "Type", render: (v: unknown) => <span className="text-white">{String(v).replace(/_/g, " ")}</span> },
    {
      key: "user_name",
      label: "User",
      render: (v: unknown, row: FraudAlert) => (
        <span className="text-slate-300">{v ? String(v) : row.user_id ? `#${row.user_id}` : "—"}</span>
      ),
    },
    { key: "description", label: "Description", render: (v: unknown) => <span className="text-slate-400">{v ? String(v) : "—"}</span> },
    {
      key: "status",
      label: "Status",
      render: (v: unknown) => <span className="text-slate-300">{String(v).replace(/_/g, " ")}</span>,
    },
    {
      key: "created_at",
      label: "Raised",
      render: (v: unknown) => (
        <span className="text-slate-400">
          {new Date(String(v)).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" })}
        </span>
      ),
    },
    {
      key: "id",
      label: "Actions",
      render: (id: unknown, row: FraudAlert) => {
        const alertId = Number(id);
        const disabled = busyId === alertId || !["open", "investigating"].includes(row.status);
        return (
          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={disabled}
              onClick={() => decide(alertId, "resolved_genuine")}
              className="rounded-lg px-2 py-1 text-xs font-semibold text-emerald-400 transition hover:bg-emerald-500/10 disabled:opacity-30"
            >
              Genuine
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => decide(alertId, "resolved_fraud")}
              className="rounded-lg px-2 py-1 text-xs font-semibold text-rose-400 transition hover:bg-rose-500/10 disabled:opacity-30"
            >
              Fraud
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => decide(alertId, "false_positive")}
              className="rounded-lg px-2 py-1 text-xs font-semibold text-slate-400 transition hover:bg-white/10 disabled:opacity-30"
            >
              False positive
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
          aria-label="Filter alerts by status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white outline-none focus:border-amber-400/60"
        >
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="investigating">Investigating</option>
          <option value="resolved_genuine">Resolved (genuine)</option>
          <option value="resolved_fraud">Resolved (fraud)</option>
          <option value="false_positive">False positive</option>
        </select>
      </div>
      <DataTable columns={columns} data={alerts} keyField="id" loading={loading} error={error} onRetry={fetchAlerts} />
      <p className="text-sm text-slate-400">
        Showing <span className="font-semibold text-white">{alerts.length}</span> of{" "}
        <span className="font-semibold text-white">{total}</span> alerts
      </p>
    </div>
  );
}

function UnderwritingTab() {
  const [items, setItems] = useState<UnderwritingItem[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<UnderwritingDetail | null>(null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const query = statusFilter ? `?status_filter=${statusFilter}&limit=100` : "?limit=100";
      const response = await adminApi.get<{ items: UnderwritingItem[]; pagination: { total: number } }>(
        `/admin/risk/underwriting-queue${query}`
      );
      setItems(response.items);
      setTotal(response.pagination.total);
      setError(null);
    } catch (err) {
      setItems([]);
      setError(toErrorMessage(err, "Failed to load underwriting queue."));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const openDetail = async (id: number) => {
    const detail = await adminApi.get<UnderwritingDetail>(`/admin/risk/underwriting-queue/${id}`);
    setSelected(detail);
    setNotes(detail.notes ?? "");
  };

  const decide = async (status: "resolved" | "escalated", assignToMe: boolean) => {
    if (!selected) return;
    setBusy(true);
    try {
      await adminApi.post(`/admin/risk/underwriting-queue/${selected.id}/decision`, {
        status,
        notes: notes || undefined,
        assign_to_me: assignToMe,
      });
      setSelected(null);
      await fetchItems();
    } finally {
      setBusy(false);
    }
  };

  const columns = [
    {
      key: "entity_name",
      label: "Applicant",
      render: (v: unknown, row: UnderwritingItem) => (
        <span className="text-white">{v ? String(v) : `${row.entity_type} #${row.entity_id}`}</span>
      ),
    },
    { key: "queue_type", label: "Queue", render: (v: unknown) => <span className="text-slate-400">{String(v).replace(/_/g, " ")}</span> },
    { key: "priority", label: "Priority", render: (v: unknown) => <span className="text-slate-300">P{String(v)}</span> },
    { key: "status", label: "Status", render: (v: unknown) => <span className="text-slate-300">{String(v).replace(/_/g, " ")}</span> },
    {
      key: "sla_breached",
      label: "SLA",
      render: (v: unknown) =>
        v ? (
          <span className="rounded-full bg-rose-500/20 px-3 py-1 text-xs font-semibold text-rose-400">Breached</span>
        ) : (
          <span className="text-slate-500">On track</span>
        ),
    },
    { key: "assigned_to_email", label: "Assigned", render: (v: unknown) => <span className="text-slate-400">{v ? String(v) : "Unassigned"}</span> },
    {
      key: "id",
      label: "",
      render: (id: unknown) => (
        <button
          type="button"
          onClick={() => openDetail(Number(id))}
          className="rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold text-white hover:bg-white/20"
        >
          Review
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <select
          aria-label="Filter underwriting queue by status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white outline-none focus:border-amber-400/60"
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="in_review">In review</option>
          <option value="resolved">Resolved</option>
          <option value="escalated">Escalated</option>
        </select>
      </div>
      <DataTable columns={columns} data={items} keyField="id" loading={loading} error={error} onRetry={fetchItems} />
      <p className="text-sm text-slate-400">
        Showing <span className="font-semibold text-white">{items.length}</span> of{" "}
        <span className="font-semibold text-white">{total}</span> items
      </p>

      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setSelected(null)}>
          <div
            className="glass-panel max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-[2rem] p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-white">Underwriting dossier — {selected.entity_type} #{selected.entity_id}</h3>
            {selected.user_context && (
              <div className="mt-4 grid gap-3 sm:grid-cols-2 text-sm">
                <p className="text-slate-400">Name <span className="block text-white">{selected.user_context.name ?? "—"}</span></p>
                <p className="text-slate-400">Phone <span className="block text-white">{selected.user_context.phone}</span></p>
                <p className="text-slate-400">Credit limit <span className="block text-white">PKR {selected.user_context.credit_limit.toLocaleString()}</span></p>
                <p className="text-slate-400">Available credit <span className="block text-white">PKR {selected.user_context.available_credit.toLocaleString()}</span></p>
                <p className="text-slate-400">Risk band <span className="block text-white">{selected.user_context.risk_band ?? "—"}</span></p>
                <p className="text-slate-400">Status <span className="block text-white">{selected.user_context.status}</span></p>
              </div>
            )}
            {selected.bank_statement_analysis ? (
              <div className="mt-4 rounded-xl bg-white/5 p-4 text-sm">
                <p className="font-medium text-white">Bank statement analysis</p>
                <div className="mt-2 grid gap-2 sm:grid-cols-2 text-slate-300">
                  <p>Period: {selected.bank_statement_analysis.period_start} to {selected.bank_statement_analysis.period_end}</p>
                  <p>Salary detected: {selected.bank_statement_analysis.salary_detected ? "Yes" : "No"}</p>
                  <p>Avg balance: {selected.bank_statement_analysis.avg_balance != null ? `PKR ${selected.bank_statement_analysis.avg_balance.toLocaleString()}` : "—"}</p>
                  <p>Income estimate: {selected.bank_statement_analysis.income_estimate != null ? `PKR ${selected.bank_statement_analysis.income_estimate.toLocaleString()}` : "—"}</p>
                  <p>Expense ratio: {selected.bank_statement_analysis.expense_ratio != null ? `${(selected.bank_statement_analysis.expense_ratio * 100).toFixed(1)}%` : "—"}</p>
                  <p>NSF events: {selected.bank_statement_analysis.nsf_events}</p>
                </div>
              </div>
            ) : (
              <p className="mt-4 text-sm text-slate-500">No bank statement analysis on file for this applicant.</p>
            )}
            <div className="mt-4">
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Decision notes</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-amber-400/60"
                placeholder="Underwriting rationale..."
              />
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                disabled={busy}
                onClick={() => decide("resolved", true)}
                className="rounded-full bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
              >
                Approve & resolve
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => decide("escalated", true)}
                className="rounded-full bg-rose-500/80 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-500 disabled:opacity-60"
              >
                Escalate
              </button>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="rounded-full px-4 py-2 text-sm font-semibold text-slate-400 hover:text-white"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function BlacklistTab() {
  const [entries, setEntries] = useState<BlacklistEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [listError, setListError] = useState<string | null>(null);
  const [form, setForm] = useState({ entry_type: "user", value: "", reason: "", user_id: "" });

  const fetchEntries = useCallback(async () => {
    setLoading(true);
    try {
      const response = await adminApi.get<{ items: BlacklistEntry[]; pagination: { total: number } }>(
        "/admin/risk/blacklist?limit=100"
      );
      setEntries(response.items);
      setTotal(response.pagination.total);
      setListError(null);
    } catch (err) {
      setEntries([]);
      setListError(toErrorMessage(err, "Failed to load blacklist entries."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await adminApi.post("/admin/risk/blacklist", {
        entry_type: form.entry_type,
        value: form.value,
        reason: form.reason,
        user_id: form.user_id ? Number(form.user_id) : undefined,
      });
      setForm({ entry_type: "user", value: "", reason: "", user_id: "" });
      setShowForm(false);
      await fetchEntries();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add entry");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRemove = async (id: number) => {
    if (!confirm("Remove this blacklist entry?")) return;
    await adminApi.delete(`/admin/risk/blacklist/${id}`);
    await fetchEntries();
  };

  const columns = [
    {
      key: "entry_type",
      label: "Type",
      render: (type: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${entryTypeStyles[String(type)] || "bg-slate-500/20 text-slate-400"}`}>
          {String(type)}
        </span>
      ),
    },
    { key: "value", label: "Value", render: (v: unknown) => <span className="font-mono text-sm text-white">{String(v)}</span> },
    { key: "reason", label: "Reason", render: (v: unknown) => <span className="text-slate-400">{String(v)}</span> },
    {
      key: "user_id",
      label: "Linked User",
      render: (v: unknown) => <span className="text-slate-400">{v ? `#${v}` : "—"}</span>,
    },
    {
      key: "created_at",
      label: "Added",
      render: (v: unknown) => (
        <span className="text-slate-400">
          {new Date(String(v)).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" })}
        </span>
      ),
    },
    {
      key: "id",
      label: "",
      render: (id: unknown) => (
        <button
          type="button"
          onClick={() => handleRemove(Number(id))}
          className="rounded-lg p-2 text-slate-400 transition hover:bg-rose-500/10 hover:text-rose-400"
          title="Remove from blacklist"
        >
          <Trash2 className="h-4 w-4" />
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
          className="flex items-center gap-2 rounded-full bg-amber-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-300"
        >
          <Plus className="h-4 w-4" />
          Add entry
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleAdd} className="glass-panel space-y-4 rounded-[2rem] p-5">
          <h3 className="text-lg font-semibold text-white">Add blacklist entry</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Type</label>
              <select
                aria-label="Blacklist entry type"
                value={form.entry_type}
                onChange={(e) => setForm({ ...form, entry_type: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-amber-400/60"
              >
                <option value="user">User</option>
                <option value="device">Device</option>
                <option value="ip">IP Address</option>
                <option value="phone">Phone (E.164, e.g. +923001234567)</option>
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Value</label>
              <input
                required
                value={form.value}
                onChange={(e) => setForm({ ...form, value: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-amber-400/60"
                placeholder={form.entry_type === "phone" ? "+923001234567" : "Value to blacklist"}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Linked User ID (optional)</label>
              <input
                value={form.user_id}
                onChange={(e) => setForm({ ...form, user_id: e.target.value.replace(/\D/g, "") })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-amber-400/60"
                placeholder="e.g. 123"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Reason</label>
              <input
                required
                minLength={3}
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none focus:border-amber-400/60"
                placeholder="Why is this being blacklisted?"
              />
            </div>
          </div>
          {error && <p className="text-sm text-rose-400">{error}</p>}
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={submitting}
              className="rounded-full bg-amber-400 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-amber-300 disabled:opacity-60"
            >
              {submitting ? "Adding..." : "Add to blacklist"}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-full px-5 py-2.5 text-sm font-semibold text-slate-400 hover:text-white"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <DataTable columns={columns} data={entries} keyField="id" loading={loading} error={listError} onRetry={fetchEntries} />
      <p className="text-sm text-slate-400">
        Showing <span className="font-semibold text-white">{entries.length}</span> of{" "}
        <span className="font-semibold text-white">{total}</span> entries
      </p>
    </div>
  );
}
