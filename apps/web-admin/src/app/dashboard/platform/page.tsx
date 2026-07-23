"use client";

import { Activity, Database, Pencil, Save, Server, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorBanner, toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface SystemHealth {
  status: string;
  components: Record<string, { status: string }>;
  metrics: { metric_name: string; value: number; recorded_at: string }[];
  queue_depth: number;
  failed_jobs_24h: number;
  timestamp: string;
}

interface SystemParameters {
  parameters: Record<string, string | number | boolean>;
  cached: boolean;
}

export default function PlatformOpsPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [params, setParams] = useState<Record<string, string | number | boolean>>({});
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    const [h, p] = await Promise.all([
      adminApi.get<SystemHealth>("/admin/system/health"),
      adminApi.get<SystemParameters>("/admin/system/parameters"),
    ]);
    setHealth(h);
    setParams(p.parameters);
  }, []);

  const loadAll = useCallback(() => {
    setLoading(true);
    fetchAll()
      .then(() => setError(null))
      .catch((err) => setError(toErrorMessage(err, "Failed to load platform operations data.")))
      .finally(() => setLoading(false));
  }, [fetchAll]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const startEdit = (key: string, value: string | number | boolean) => {
    setEditingKey(key);
    setEditValue(String(value));
  };

  const saveEdit = async () => {
    if (!editingKey) return;
    setSaving(true);
    try {
      const original = params[editingKey];
      let coerced: string | number | boolean = editValue;
      if (typeof original === "number") coerced = Number(editValue);
      if (typeof original === "boolean") coerced = editValue === "true";
      await adminApi.put(`/admin/system/parameters/${editingKey}`, { value: coerced });
      setParams((prev) => ({ ...prev, [editingKey]: coerced }));
      setEditingKey(null);
    } finally {
      setSaving(false);
    }
  };

  const componentEntries = health ? Object.entries(health.components) : [];
  const paramEntries = Object.entries(params).sort(([a], [b]) => a.localeCompare(b));

  if (loading) {
    return (
      <section className="space-y-6">
        <div className="h-40 animate-pulse rounded-2xl bg-slate-900/50" />
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-27 / AD-28</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Platform operations &amp; system health</h2>
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={loadAll} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Activity className={`h-4 w-4 ${health?.status === "ok" ? "text-emerald-500" : "text-amber-500"}`} />
            System Status
          </div>
          <p className={`mt-2 text-2xl font-bold ${health?.status === "ok" ? "text-emerald-400" : "text-amber-400"}`}>
            {health?.status === "ok" ? "Operational" : "Degraded"}
          </p>
        </div>
        {componentEntries.map(([name, comp]) => (
          <div key={name} className="glass-panel rounded-xl p-4">
            <div className="flex items-center gap-2 text-sm text-slate-400">
              {name === "database" ? <Database className="h-4 w-4 text-blue-500" /> : <Server className="h-4 w-4 text-blue-500" />}
              {name.charAt(0).toUpperCase() + name.slice(1)}
            </div>
            <p className={`mt-2 text-2xl font-bold ${comp.status === "up" ? "text-white" : "text-rose-400"}`}>
              {comp.status === "up" ? "Up" : "Down"}
            </p>
          </div>
        ))}
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Server className="h-4 w-4 text-amber-500" />
            Job Queue Depth
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{health?.queue_depth ?? 0}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Server className="h-4 w-4 text-rose-500" />
            Failed Jobs (24h)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{health?.failed_jobs_24h ?? 0}</p>
        </div>
      </div>

      {health && health.metrics.length > 0 && (
        <section className="glass-panel rounded-[2rem] p-5">
          <h3 className="text-lg font-semibold text-white">System health metrics</h3>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {health.metrics.map((m) => (
              <div key={m.metric_name} className="rounded-xl bg-white/5 px-4 py-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">{m.metric_name.replace(/_/g, " ")}</p>
                <p className="mt-1 text-lg font-semibold text-white">{m.value}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="glass-panel rounded-[2rem] p-5">
        <h3 className="text-lg font-semibold text-white">System parameters</h3>
        <p className="mt-1 text-sm text-slate-400">Operational configuration. Changes take effect immediately.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-4 py-2">Key</th>
                <th className="px-4 py-2">Value</th>
                <th className="px-4 py-2">Edit</th>
              </tr>
            </thead>
            <tbody>
              {paramEntries.map(([key, value]) => (
                <tr key={key} className="border-b border-white/5">
                  <td className="px-4 py-2 font-mono text-xs text-slate-400">{key}</td>
                  <td className="px-4 py-2 text-white">
                    {editingKey === key ? (
                      <input
                        autoFocus
                        aria-label={`Value for ${key}`}
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        className="w-full rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-sm text-white outline-none focus:border-amber-400/60"
                      />
                    ) : (
                      String(value)
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {editingKey === key ? (
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          disabled={saving}
                          onClick={saveEdit}
                          className="rounded-lg p-1.5 text-emerald-400 hover:bg-emerald-500/10"
                          title="Save"
                        >
                          <Save className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingKey(null)}
                          className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10"
                          title="Cancel"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => startEdit(key, value)}
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 hover:text-white"
                        title="Edit"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
