"use client";

import { Gift, Megaphone, Plus, Users2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable } from "@/components/admin/data-table";
import { ErrorBanner, toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface Campaign {
  id: number;
  name: string;
  channel: string;
  budget: number | null;
  spend: number;
  start_date: string;
  end_date: string | null;
  status: string;
}

interface PromoCode {
  id: number;
  code: string;
  promo_type: string;
  discount_value: number | null;
  discount_pct: number | null;
  usage_limit_total: number | null;
  times_used: number;
  valid_until: string;
  is_active: boolean;
}

interface ReferralsSummary {
  by_status: Record<string, number>;
  total_rewards_paid: number;
}

const TABS = [
  { key: "campaigns", label: "Campaigns" },
  { key: "promos", label: "Promo Codes" },
  { key: "referrals", label: "Referrals" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function MarketingPage() {
  const [tab, setTab] = useState<TabKey>("campaigns");

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-29</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Marketing &amp; growth</h2>
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

      {tab === "campaigns" && <CampaignsTab />}
      {tab === "promos" && <PromosTab />}
      {tab === "referrals" && <ReferralsTab />}
    </section>
  );
}

function CampaignsTab() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", channel: "sms_blast", budget: "", start_date: "", end_date: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchCampaigns = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.get<{ items: Campaign[] }>("/admin/marketing/campaigns");
      setCampaigns(r.items);
      setError(null);
    } catch (err) {
      setCampaigns([]);
      setError(toErrorMessage(err, "Failed to load campaigns."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCampaigns();
  }, [fetchCampaigns]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await adminApi.post("/admin/marketing/campaigns", {
        name: form.name,
        channel: form.channel,
        budget: form.budget ? Number(form.budget) : undefined,
        start_date: form.start_date,
        end_date: form.end_date || undefined,
      });
      setForm({ name: "", channel: "sms_blast", budget: "", start_date: "", end_date: "" });
      setShowForm(false);
      await fetchCampaigns();
    } finally {
      setSubmitting(false);
    }
  };

  const columns = [
    { key: "name", label: "Campaign", render: (v: unknown) => <span className="font-medium text-white">{String(v)}</span> },
    { key: "channel", label: "Channel", render: (v: unknown) => <span className="text-slate-300">{String(v).replace(/_/g, " ")}</span> },
    { key: "budget", label: "Budget", render: (v: unknown) => <span className="text-slate-300">{v != null ? `PKR ${Number(v).toLocaleString()}` : "—"}</span> },
    { key: "spend", label: "Spend", render: (v: unknown) => <span className="text-slate-400">PKR {Number(v).toLocaleString()}</span> },
    { key: "status", label: "Status", render: (v: unknown) => <span className="text-slate-300">{String(v)}</span> },
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
          New campaign
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="glass-panel space-y-4 rounded-[2rem] p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Name</label>
              <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Channel</label>
              <select
                aria-label="Channel"
                value={form.channel}
                onChange={(e) => setForm({ ...form, channel: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none"
              >
                <option value="meta_ads">Meta Ads</option>
                <option value="google">Google</option>
                <option value="sms_blast">SMS Blast</option>
                <option value="influencer">Influencer</option>
                <option value="email">Email</option>
                <option value="tiktok">TikTok</option>
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Budget (PKR)</label>
              <input type="number" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Start date</label>
              <input required type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">End date (optional)</label>
              <input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={submitting} className="rounded-full bg-amber-400 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-amber-300 disabled:opacity-60">
              {submitting ? "Creating..." : "Create campaign"}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className="rounded-full px-5 py-2.5 text-sm font-semibold text-slate-400 hover:text-white">
              Cancel
            </button>
          </div>
        </form>
      )}

      <DataTable columns={columns} data={campaigns} keyField="id" loading={loading} error={error} onRetry={fetchCampaigns} />
    </div>
  );
}

function PromosTab() {
  const [promos, setPromos] = useState<PromoCode[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ code: "", promo_type: "cashback_pct", discount_pct: "", valid_from: "", valid_until: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPromos = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.get<{ items: PromoCode[] }>("/admin/marketing/promo-codes");
      setPromos(r.items);
      setError(null);
    } catch (err) {
      setPromos([]);
      setError(toErrorMessage(err, "Failed to load promo codes."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPromos();
  }, [fetchPromos]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await adminApi.post("/admin/marketing/promo-codes", {
        code: form.code,
        promo_type: form.promo_type,
        discount_pct: form.discount_pct ? Number(form.discount_pct) : undefined,
        valid_from: form.valid_from,
        valid_until: form.valid_until,
      });
      setForm({ code: "", promo_type: "cashback_pct", discount_pct: "", valid_from: "", valid_until: "" });
      setShowForm(false);
      await fetchPromos();
    } finally {
      setSubmitting(false);
    }
  };

  const columns = [
    { key: "code", label: "Code", render: (v: unknown) => <span className="font-mono text-sm font-semibold text-white">{String(v)}</span> },
    { key: "promo_type", label: "Type", render: (v: unknown) => <span className="text-slate-300">{String(v).replace(/_/g, " ")}</span> },
    { key: "discount_pct", label: "Discount", render: (v: unknown, row: PromoCode) => <span className="text-slate-300">{v != null ? `${v}%` : row.discount_value != null ? `PKR ${row.discount_value}` : "—"}</span> },
    { key: "times_used", label: "Used", render: (v: unknown, row: PromoCode) => <span className="text-slate-400">{String(v)}{row.usage_limit_total ? ` / ${row.usage_limit_total}` : ""}</span> },
    { key: "valid_until", label: "Expires", render: (v: unknown) => <span className="text-slate-400">{new Date(String(v)).toLocaleDateString()}</span> },
    {
      key: "is_active",
      label: "Status",
      render: (v: unknown) => <span className={v ? "text-emerald-400" : "text-slate-500"}>{v ? "Active" : "Inactive"}</span>,
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
          New promo code
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="glass-panel space-y-4 rounded-[2rem] p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Code</label>
              <input required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Type</label>
              <select
                aria-label="Promo type"
                value={form.promo_type}
                onChange={(e) => setForm({ ...form, promo_type: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none"
              >
                <option value="fee_waiver">Fee waiver</option>
                <option value="credit_bonus">Credit bonus</option>
                <option value="cashback_pct">Cashback %</option>
                <option value="cashback_flat">Cashback flat</option>
                <option value="free_delivery">Free delivery</option>
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Discount %</label>
              <input type="number" value={form.discount_pct} onChange={(e) => setForm({ ...form, discount_pct: e.target.value })} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Valid from</label>
              <input required type="date" value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Valid until</label>
              <input required type="date" value={form.valid_until} onChange={(e) => setForm({ ...form, valid_until: e.target.value })} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={submitting} className="rounded-full bg-amber-400 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-amber-300 disabled:opacity-60">
              {submitting ? "Creating..." : "Create code"}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className="rounded-full px-5 py-2.5 text-sm font-semibold text-slate-400 hover:text-white">
              Cancel
            </button>
          </div>
        </form>
      )}

      <DataTable columns={columns} data={promos} keyField="id" loading={loading} error={error} onRetry={fetchPromos} />
    </div>
  );
}

function ReferralsTab() {
  const [summary, setSummary] = useState<ReferralsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(() => {
    adminApi
      .get<ReferralsSummary>("/admin/marketing/referrals/summary")
      .then((r) => {
        setSummary(r);
        setError(null);
      })
      .catch((err) => setError(toErrorMessage(err, "Failed to load referrals summary.")));
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} onRetry={fetchSummary} />}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Gift className="h-4 w-4 text-emerald-500" />
            Rewards Paid
          </div>
          <p className="mt-2 text-2xl font-bold text-white">PKR {(summary?.total_rewards_paid ?? 0).toLocaleString()}</p>
        </div>
        {Object.entries(summary?.by_status ?? {}).map(([status, count]) => (
          <div key={status} className="glass-panel rounded-xl p-4">
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <Users2 className="h-4 w-4 text-blue-500" />
              {status}
            </div>
            <p className="mt-2 text-2xl font-bold text-white">{count}</p>
          </div>
        ))}
      </div>
      {(!summary || Object.keys(summary.by_status).length === 0) && (
        <div className="glass-panel rounded-2xl p-8 text-center">
          <Megaphone className="mx-auto h-8 w-8 text-slate-600" />
          <p className="mt-2 text-sm text-slate-500">No referral activity recorded yet.</p>
        </div>
      )}
    </div>
  );
}
