"use client";

import { CreditCard, Plug, Receipt } from "lucide-react";
import { useEffect, useState } from "react";
import { adminApi } from "@/lib/api-client";

interface ParametersResponse {
  parameters: Record<string, string | number | boolean>;
}

interface Integration {
  id: number;
  name: string;
  category: string;
  status: string;
  last_checked_at: string | null;
}

const statusStyles: Record<string, string> = {
  not_configured: "bg-slate-500/20 text-slate-400",
  configured: "bg-blue-500/20 text-blue-400",
  healthy: "bg-emerald-500/20 text-emerald-400",
  degraded: "bg-amber-500/20 text-amber-400",
  failed: "bg-rose-500/20 text-rose-400",
};

const PLAN_TIERS = [
  { key: "3m", label: "3 months" },
  { key: "4m", label: "4 months" },
  { key: "6m", label: "6 months" },
  { key: "12m", label: "12 months" },
] as const;

const FEE_FIELDS = [
  { key: "processing_fee_pct", label: "Processing fee (%)" },
  { key: "early_settlement_fee_pct", label: "Early settlement fee (%)" },
  { key: "restructuring_fee_pkr", label: "Restructuring fee (PKR)" },
  { key: "dishonored_payment_fee_pkr", label: "Dishonored payment fee (PKR)" },
  { key: "late_fee_rate_pkr_per_day", label: "Late fee (PKR/day)" },
] as const;

const TABS = [
  { key: "plans", label: "Payment Plans" },
  { key: "fees", label: "Fee Structure" },
  { key: "integrations", label: "Integrations" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function SettingsPage() {
  const [tab, setTab] = useState<TabKey>("plans");

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-26</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">System settings</h2>
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

      {tab === "plans" && <PaymentPlansTab />}
      {tab === "fees" && <FeeStructureTab />}
      {tab === "integrations" && <IntegrationsTab />}
    </section>
  );
}

function PaymentPlansTab() {
  const [params, setParams] = useState<Record<string, string | number | boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    adminApi
      .get<ParametersResponse>("/admin/system/parameters")
      .then((r) => setParams(r.parameters))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const payload: Record<string, unknown> = {};
      for (const tier of PLAN_TIERS) {
        payload[`plan_${tier.key}_enabled`] = params[`plan_${tier.key}_enabled`];
        payload[`plan_${tier.key}_max_amount_pkr`] = Number(params[`plan_${tier.key}_max_amount_pkr`]);
        payload[`profit_rate_${tier.key}`] = Number(params[`profit_rate_${tier.key}`]);
      }
      await adminApi.put("/admin/system/parameters", { parameters: payload });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="h-40 animate-pulse rounded-2xl bg-slate-900/50" />;

  return (
    <div className="glass-panel space-y-4 rounded-[2rem] p-5">
      <div className="flex items-center gap-2">
        <CreditCard className="h-5 w-5 text-blue-400" />
        <h3 className="text-lg font-semibold text-white">Payment plan configuration</h3>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {PLAN_TIERS.map((tier) => (
          <div key={tier.key} className="rounded-xl bg-white/5 p-4">
            <div className="flex items-center justify-between">
              <h4 className="font-medium text-white">{tier.label}</h4>
              <label className="flex items-center gap-2 text-xs text-slate-400">
                <input
                  type="checkbox"
                  checked={Boolean(params[`plan_${tier.key}_enabled`])}
                  onChange={(e) => setParams({ ...params, [`plan_${tier.key}_enabled`]: e.target.checked })}
                />
                Enabled
              </label>
            </div>
            <div className="mt-3 space-y-2">
              <div>
                <label className="mb-1 block text-xs text-slate-400">Profit rate (%)</label>
                <input
                  type="number"
                  step="0.1"
                  value={String(params[`profit_rate_${tier.key}`] ?? "")}
                  onChange={(e) => setParams({ ...params, [`profit_rate_${tier.key}`]: e.target.value })}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-400">Max order amount (PKR)</label>
                <input
                  type="number"
                  value={String(params[`plan_${tier.key}_max_amount_pkr`] ?? "")}
                  onChange={(e) => setParams({ ...params, [`plan_${tier.key}_max_amount_pkr`]: e.target.value })}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none"
                />
              </div>
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={saving}
          onClick={handleSave}
          className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60"
        >
          {saving ? "Saving..." : "Save plan configuration"}
        </button>
        {saved && <span className="text-sm text-emerald-400">Saved</span>}
      </div>
    </div>
  );
}

function FeeStructureTab() {
  const [params, setParams] = useState<Record<string, string | number | boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    adminApi
      .get<ParametersResponse>("/admin/system/parameters")
      .then((r) => setParams(r.parameters))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const payload: Record<string, unknown> = {};
      for (const f of FEE_FIELDS) {
        payload[f.key] = Number(params[f.key]);
      }
      await adminApi.put("/admin/system/parameters", { parameters: payload });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="h-40 animate-pulse rounded-2xl bg-slate-900/50" />;

  return (
    <div className="glass-panel space-y-4 rounded-[2rem] p-5">
      <div className="flex items-center gap-2">
        <Receipt className="h-5 w-5 text-amber-400" />
        <h3 className="text-lg font-semibold text-white">Fee structure configuration</h3>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {FEE_FIELDS.map((f) => (
          <div key={f.key}>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">{f.label}</label>
            <input
              type="number"
              step="0.01"
              value={String(params[f.key] ?? "")}
              onChange={(e) => setParams({ ...params, [f.key]: e.target.value })}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none"
            />
          </div>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={saving}
          onClick={handleSave}
          className="rounded-full bg-amber-400 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-amber-300 disabled:opacity-60"
        >
          {saving ? "Saving..." : "Save fee structure"}
        </button>
        {saved && <span className="text-sm text-emerald-400">Saved</span>}
      </div>
    </div>
  );
}

function IntegrationsTab() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchIntegrations = () => {
    adminApi
      .get<{ items: Integration[] }>("/admin/system/integrations")
      .then((r) => setIntegrations(r.items))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchIntegrations();
  }, []);

  const handleMarkConfigured = async (id: number) => {
    await adminApi.put(`/admin/system/integrations/${id}`, { status: "configured" });
    fetchIntegrations();
  };

  if (loading) return <div className="h-40 animate-pulse rounded-2xl bg-slate-900/50" />;

  return (
    <div className="glass-panel rounded-[2rem] p-5">
      <div className="mb-4 flex items-center gap-2">
        <Plug className="h-5 w-5 text-purple-400" />
        <h3 className="text-lg font-semibold text-white">Third-party integrations</h3>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {integrations.map((i) => (
          <div key={i.id} className="rounded-xl bg-white/5 p-4">
            <div className="flex items-center justify-between">
              <h4 className="font-medium text-white">{i.name}</h4>
              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusStyles[i.status] || ""}`}>
                {i.status.replace(/_/g, " ")}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">{i.category.replace(/_/g, " ")}</p>
            {i.status === "not_configured" && (
              <button
                type="button"
                onClick={() => handleMarkConfigured(i.id)}
                className="mt-3 rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold text-white hover:bg-white/20"
              >
                Mark configured
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
