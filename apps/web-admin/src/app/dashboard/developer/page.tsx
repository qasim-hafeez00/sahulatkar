"use client";

import { Key, Plus, Trash2, Webhook } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable } from "@/components/admin/data-table";
import { ErrorBanner, toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface ApiKeyItem {
  id: number;
  merchant_name: string | null;
  partner_name: string | null;
  key_prefix: string;
  scopes: string[];
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

interface WebhookItem {
  id: number;
  merchant_name: string | null;
  endpoint_url: string;
  events: string[];
  is_active: boolean;
  created_at: string;
}

interface IntegrationLog {
  id: number;
  service_name: string;
  operation: string;
  response_code: number | null;
  latency_ms: number | null;
  is_success: boolean | null;
  created_at: string;
}

interface DeveloperSummary {
  active_api_keys: number;
  active_webhooks: number;
  integration_calls_24h: number;
  integration_success_rate_24h: number | null;
}

const TABS = [
  { key: "keys", label: "API Keys" },
  { key: "webhooks", label: "Webhooks" },
  { key: "logs", label: "Integration Logs" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function DeveloperPage() {
  const [tab, setTab] = useState<TabKey>("keys");
  const [summary, setSummary] = useState<DeveloperSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const fetchSummary = useCallback(() => {
    adminApi
      .get<DeveloperSummary>("/admin/developer/summary")
      .then((r) => {
        setSummary(r);
        setSummaryError(null);
      })
      .catch((err) => setSummaryError(toErrorMessage(err, "Failed to load developer summary.")));
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [tab, fetchSummary]);

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-30</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">API &amp; developer tools</h2>
      </div>

      {summaryError && <ErrorBanner message={summaryError} onRetry={fetchSummary} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Key className="h-4 w-4 text-blue-500" />
            Active API Keys
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{summary?.active_api_keys ?? 0}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Webhook className="h-4 w-4 text-purple-500" />
            Active Webhooks
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{summary?.active_webhooks ?? 0}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Webhook className="h-4 w-4 text-emerald-500" />
            Integration Calls (24h)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{summary?.integration_calls_24h ?? 0}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Webhook className="h-4 w-4 text-amber-500" />
            Success Rate (24h)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">
            {summary?.integration_success_rate_24h != null ? `${summary.integration_success_rate_24h}%` : "—"}
          </p>
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

      {tab === "keys" && <ApiKeysTab />}
      {tab === "webhooks" && <WebhooksTab />}
      {tab === "logs" && <IntegrationLogsTab />}
    </section>
  );
}

function ApiKeysTab() {
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [partnerName, setPartnerName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchKeys = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.get<{ items: ApiKeyItem[] }>("/admin/developer/api-keys");
      setKeys(r.items);
      setError(null);
    } catch (err) {
      setKeys([]);
      setError(toErrorMessage(err, "Failed to load API keys."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const r = await adminApi.post<{ api_key: string }>("/admin/developer/api-keys", { partner_name: partnerName, scopes: ["read"] });
      setNewKey(r.api_key);
      setPartnerName("");
      await fetchKeys();
    } finally {
      setSubmitting(false);
    }
  };

  const handleRevoke = async (id: number) => {
    if (!confirm("Revoke this API key? Any integration using it will stop working immediately.")) return;
    await adminApi.delete(`/admin/developer/api-keys/${id}`);
    await fetchKeys();
  };

  const columns = [
    { key: "partner_name", label: "Partner", render: (v: unknown) => <span className="font-medium text-white">{v ? String(v) : "—"}</span> },
    { key: "key_prefix", label: "Key Prefix", render: (v: unknown) => <span className="font-mono text-sm text-slate-300">{String(v)}...</span> },
    { key: "scopes", label: "Scopes", render: (v: unknown) => <span className="text-slate-400">{(v as string[]).join(", ")}</span> },
    {
      key: "is_active",
      label: "Status",
      render: (v: unknown) => <span className={v ? "text-emerald-400" : "text-rose-400"}>{v ? "Active" : "Revoked"}</span>,
    },
    {
      key: "actions",
      label: "",
      render: (_v: unknown, row: ApiKeyItem) =>
        row.is_active ? (
          <button
            type="button"
            onClick={() => handleRevoke(row.id)}
            className="rounded-lg p-2 text-slate-400 hover:bg-rose-500/10 hover:text-rose-400"
            title="Revoke"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setShowForm((s) => !s)}
          className="flex items-center gap-2 rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          <Plus className="h-4 w-4" />
          New API Key
        </button>
      </div>

      {newKey && (
        <div className="glass-panel rounded-[2rem] p-5">
          <p className="text-sm text-amber-300">Copy this key now — it will not be shown again.</p>
          <p className="mt-2 rounded-lg bg-black/30 px-4 py-2 font-mono text-sm text-white break-all">{newKey}</p>
          <button type="button" onClick={() => setNewKey(null)} className="mt-3 rounded-full px-4 py-2 text-sm font-semibold text-slate-400 hover:text-white">
            Done
          </button>
        </div>
      )}

      {showForm && !newKey && (
        <form onSubmit={handleCreate} className="glass-panel space-y-4 rounded-[2rem] p-5">
          <div>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Partner name</label>
            <input required value={partnerName} onChange={(e) => setPartnerName(e.target.value)} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
          </div>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={submitting} className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60">
              {submitting ? "Creating..." : "Create key"}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className="rounded-full px-5 py-2.5 text-sm font-semibold text-slate-400 hover:text-white">
              Cancel
            </button>
          </div>
        </form>
      )}

      <DataTable columns={columns} data={keys} keyField="id" loading={loading} error={error} onRetry={fetchKeys} />
    </div>
  );
}

function WebhooksTab() {
  const [webhooks, setWebhooks] = useState<WebhookItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchWebhooks = useCallback(() => {
    setLoading(true);
    adminApi
      .get<{ items: WebhookItem[] }>("/admin/developer/webhooks")
      .then((r) => {
        setWebhooks(r.items);
        setError(null);
      })
      .catch((err) => {
        setWebhooks([]);
        setError(toErrorMessage(err, "Failed to load webhooks."));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchWebhooks();
  }, [fetchWebhooks]);

  const columns = [
    { key: "merchant_name", label: "Merchant", render: (v: unknown) => <span className="text-white">{v ? String(v) : "—"}</span> },
    { key: "endpoint_url", label: "Endpoint", render: (v: unknown) => <span className="font-mono text-xs text-slate-300">{String(v)}</span> },
    { key: "events", label: "Events", render: (v: unknown) => <span className="text-slate-400">{(v as string[]).join(", ")}</span> },
    {
      key: "is_active",
      label: "Status",
      render: (v: unknown) => <span className={v ? "text-emerald-400" : "text-slate-500"}>{v ? "Active" : "Inactive"}</span>,
    },
  ];

  return <DataTable columns={columns} data={webhooks} keyField="id" loading={loading} error={error} onRetry={fetchWebhooks} />;
}

function IntegrationLogsTab() {
  const [logs, setLogs] = useState<IntegrationLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = useCallback(() => {
    setLoading(true);
    adminApi
      .get<{ items: IntegrationLog[] }>("/admin/developer/integration-logs?limit=100")
      .then((r) => {
        setLogs(r.items);
        setError(null);
      })
      .catch((err) => {
        setLogs([]);
        setError(toErrorMessage(err, "Failed to load integration logs."));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const columns = [
    { key: "service_name", label: "Service", render: (v: unknown) => <span className="font-mono text-sm text-white">{String(v)}</span> },
    { key: "operation", label: "Operation", render: (v: unknown) => <span className="text-slate-300">{String(v)}</span> },
    { key: "response_code", label: "Code", render: (v: unknown) => <span className="text-slate-400">{v != null ? String(v) : "—"}</span> },
    { key: "latency_ms", label: "Latency", render: (v: unknown) => <span className="text-slate-400">{v != null ? `${v}ms` : "—"}</span> },
    {
      key: "is_success",
      label: "Result",
      render: (v: unknown) => <span className={v ? "text-emerald-400" : "text-rose-400"}>{v ? "Success" : "Failed"}</span>,
    },
    { key: "created_at", label: "Time", render: (v: unknown) => <span className="text-slate-400">{new Date(String(v)).toLocaleString()}</span> },
  ];

  return <DataTable columns={columns} data={logs} keyField="id" loading={loading} error={error} onRetry={fetchLogs} />;
}
