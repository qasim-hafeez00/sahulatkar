"use client";

import { Megaphone, Send } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable } from "@/components/admin/data-table";
import { ErrorBanner, toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface NotificationItem {
  id: number;
  user_id: number;
  category: string;
  priority: string;
  title: string;
  body: string;
  status: string;
  is_read: boolean;
  created_at: string;
}

interface NotificationsSummary {
  by_status: Record<string, number>;
  dispatches: { channel: string; status: string; count: number }[];
}

const TABS = [
  { key: "history", label: "Notification History" },
  { key: "broadcast", label: "Broadcast" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function NotificationsPage() {
  const [tab, setTab] = useState<TabKey>("history");
  const [summary, setSummary] = useState<NotificationsSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const fetchSummary = useCallback(() => {
    adminApi
      .get<NotificationsSummary>("/admin/notifications/summary")
      .then((r) => {
        setSummary(r);
        setSummaryError(null);
      })
      .catch((err) => setSummaryError(toErrorMessage(err, "Failed to load notifications summary.")));
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [tab, fetchSummary]);

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-31</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Notification center</h2>
      </div>

      {summaryError && <ErrorBanner message={summaryError} onRetry={fetchSummary} />}

      <div className="grid gap-4 sm:grid-cols-3">
        {Object.entries(summary?.by_status ?? {}).map(([status, count]) => (
          <div key={status} className="glass-panel rounded-xl p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">{status}</p>
            <p className="mt-1 text-2xl font-bold text-white">{count}</p>
          </div>
        ))}
        {!summary?.by_status || Object.keys(summary.by_status).length === 0 ? (
          <div className="glass-panel rounded-xl p-4 sm:col-span-3">
            <p className="text-sm text-slate-500">No notifications sent yet.</p>
          </div>
        ) : null}
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

      {tab === "history" && <HistoryTab />}
      {tab === "broadcast" && <BroadcastTab />}
    </section>
  );
}

function HistoryTab() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.get<{ items: NotificationItem[]; pagination: { total: number } }>("/admin/notifications?limit=100");
      setItems(r.items);
      setTotal(r.pagination.total);
      setError(null);
    } catch (err) {
      setItems([]);
      setError(toErrorMessage(err, "Failed to load notification history."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const columns = [
    { key: "title", label: "Title", render: (v: unknown) => <span className="font-medium text-white">{String(v)}</span> },
    { key: "user_id", label: "User", render: (v: unknown) => <span className="text-slate-400">#{String(v)}</span> },
    { key: "category", label: "Category", render: (v: unknown) => <span className="text-slate-300">{String(v)}</span> },
    { key: "priority", label: "Priority", render: (v: unknown) => <span className="text-slate-300">{String(v)}</span> },
    { key: "status", label: "Status", render: (v: unknown) => <span className="text-slate-300">{String(v)}</span> },
    {
      key: "created_at",
      label: "Sent",
      render: (v: unknown) => <span className="text-slate-400">{new Date(String(v)).toLocaleString()}</span>,
    },
  ];

  return (
    <div className="space-y-4">
      <DataTable columns={columns} data={items} keyField="id" loading={loading} error={error} onRetry={fetchItems} />
      <p className="text-sm text-slate-400">
        Showing <span className="font-semibold text-white">{items.length}</span> of{" "}
        <span className="font-semibold text-white">{total}</span> notifications
      </p>
    </div>
  );
}

function BroadcastTab() {
  const [segment, setSegment] = useState("all_active");
  const [userIds, setUserIds] = useState("");
  const [category, setCategory] = useState("system");
  const [priority, setPriority] = useState("normal");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [channels, setChannels] = useState<string[]>(["push"]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const toggleChannel = (c: string) => {
    setChannels((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!confirm(`Broadcast to segment "${segment}"? This cannot be undone.`)) return;
    setSubmitting(true);
    setResult(null);
    try {
      const payload: Record<string, unknown> = { segment, category, priority, title, body, channels };
      if (segment === "specific_users") {
        payload.user_ids = userIds.split(",").map((s) => Number(s.trim())).filter(Boolean);
      }
      const r = await adminApi.post<{ recipient_count: number }>("/admin/notifications/broadcast", payload);
      setResult(`Queued for ${r.recipient_count} recipient(s).`);
      setTitle("");
      setBody("");
    } catch (err) {
      setResult(err instanceof Error ? err.message : "Broadcast failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="glass-panel space-y-4 rounded-[2rem] p-5">
      <div className="flex items-center gap-2">
        <Megaphone className="h-5 w-5 text-amber-400" />
        <h3 className="text-lg font-semibold text-white">Broadcast to segment</h3>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Segment</label>
          <select
            aria-label="Broadcast segment"
            value={segment}
            onChange={(e) => setSegment(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none"
          >
            <option value="all_active">All active users</option>
            <option value="pending_kyc">Pending KYC users</option>
            <option value="specific_users">Specific user IDs</option>
          </select>
        </div>
        {segment === "specific_users" && (
          <div>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">User IDs (comma-separated)</label>
            <input
              value={userIds}
              onChange={(e) => setUserIds(e.target.value)}
              placeholder="1, 2, 3"
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none"
            />
          </div>
        )}
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Category</label>
          <input value={category} onChange={(e) => setCategory(e.target.value)} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Priority</label>
          <select
            aria-label="Priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none"
          >
            <option value="low">Low</option>
            <option value="normal">Normal</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Title</label>
          <input required value={title} onChange={(e) => setTitle(e.target.value)} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Body</label>
          <textarea required rows={3} value={body} onChange={(e) => setBody(e.target.value)} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Channels</label>
          <div className="flex gap-3">
            {["push", "sms", "email", "whatsapp"].map((c) => (
              <label key={c} className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={channels.includes(c)} onChange={() => toggleChannel(c)} />
                {c}
              </label>
            ))}
          </div>
        </div>
      </div>
      {result && <p className="text-sm text-emerald-400">{result}</p>}
      <button
        type="submit"
        disabled={submitting || channels.length === 0}
        className="flex items-center gap-2 rounded-full bg-amber-400 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-amber-300 disabled:opacity-60"
      >
        <Send className="h-4 w-4" />
        {submitting ? "Sending..." : "Send broadcast"}
      </button>
    </form>
  );
}

