"use client";

import { Building2, CheckCircle, Plus, Wallet, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable } from "@/components/admin/data-table";
import { toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface Merchant {
  id: number;
  name: string;
  domain: string | null;
  status: string;
  partner_type: string | null;
  commission_rate_pct: number | null;
  onboarding_status: string;
  product_count: number;
  created_at: string;
}

interface MerchantDetail extends Merchant {
  payment_terms_days: number | null;
  min_volume_commitment_pkr: number | null;
  order_count: number;
  total_gmv: number;
}

interface CommissionSummary {
  accrued: number;
  paid_out: number;
  accrued_count: number;
  recent_payouts: { id: number; period_start: string; period_end: string; total_amount: number; status: string; paid_at: string | null }[];
}

interface OnboardingApplication {
  id: number;
  merchant_name: string;
  domain: string | null;
  contact_name: string | null;
  contact_email: string | null;
  status: string;
  proposed_partner_type: string | null;
  proposed_commission_rate_pct: number | null;
  merchant_id: number | null;
  created_at: string;
}

const onboardingStatusStyles: Record<string, string> = {
  not_started: "bg-slate-500/20 text-slate-400",
  in_review: "bg-amber-500/20 text-amber-400",
  approved: "bg-emerald-500/20 text-emerald-400",
  rejected: "bg-rose-500/20 text-rose-400",
  active: "bg-blue-500/20 text-blue-400",
};

const TABS = [
  { key: "merchants", label: "Merchants" },
  { key: "onboarding", label: "Onboarding Applications" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function PartnersPage() {
  const [tab, setTab] = useState<TabKey>("merchants");

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-24</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Merchants &amp; partnerships</h2>
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

      {tab === "merchants" && <MerchantsTab />}
      {tab === "onboarding" && <OnboardingTab />}
    </section>
  );
}

function MerchantsTab() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<MerchantDetail | null>(null);
  const [commission, setCommission] = useState<CommissionSummary | null>(null);
  const [termsForm, setTermsForm] = useState({ partner_type: "direct_integration", commission_rate_pct: "", payment_terms_days: "", min_volume_commitment_pkr: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMerchants = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.get<{ items: Merchant[]; pagination: { total: number } }>("/admin/partners/merchants?limit=100");
      setMerchants(r.items);
      setTotal(r.pagination.total);
      setError(null);
    } catch (err) {
      setMerchants([]);
      setError(toErrorMessage(err, "Failed to load merchants."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMerchants();
  }, [fetchMerchants]);

  const openDetail = async (id: number) => {
    const detail = await adminApi.get<MerchantDetail>(`/admin/partners/merchants/${id}`);
    setSelected(detail);
    setTermsForm({
      partner_type: detail.partner_type ?? "direct_integration",
      commission_rate_pct: detail.commission_rate_pct != null ? String(detail.commission_rate_pct) : "",
      payment_terms_days: detail.payment_terms_days != null ? String(detail.payment_terms_days) : "30",
      min_volume_commitment_pkr: detail.min_volume_commitment_pkr != null ? String(detail.min_volume_commitment_pkr) : "",
    });
    const summary = await adminApi.get<CommissionSummary>(`/admin/partners/merchants/${id}/commission-summary`);
    setCommission(summary);
  };

  const handleToggleStatus = async (merchant: Merchant) => {
    const newStatus = merchant.status === "active" ? "suspended" : "active";
    if (!confirm(`Set ${merchant.name} to ${newStatus}?`)) return;
    await adminApi.put(`/admin/partners/merchants/${merchant.id}/status`, { status: newStatus });
    await fetchMerchants();
  };

  const handleSaveTerms = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    setBusy(true);
    try {
      await adminApi.put(`/admin/partners/merchants/${selected.id}/partnership`, {
        partner_type: termsForm.partner_type,
        commission_rate_pct: Number(termsForm.commission_rate_pct),
        payment_terms_days: Number(termsForm.payment_terms_days),
        min_volume_commitment_pkr: termsForm.min_volume_commitment_pkr ? Number(termsForm.min_volume_commitment_pkr) : undefined,
      });
      await openDetail(selected.id);
      await fetchMerchants();
    } finally {
      setBusy(false);
    }
  };

  const handleInitiatePayout = async () => {
    if (!selected) return;
    const periodStart = prompt("Period start (YYYY-MM-DD):");
    const periodEnd = prompt("Period end (YYYY-MM-DD):");
    if (!periodStart || !periodEnd) return;
    setBusy(true);
    try {
      await adminApi.post(`/admin/partners/merchants/${selected.id}/payouts`, { period_start: periodStart, period_end: periodEnd });
      const summary = await adminApi.get<CommissionSummary>(`/admin/partners/merchants/${selected.id}/commission-summary`);
      setCommission(summary);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to initiate payout");
    } finally {
      setBusy(false);
    }
  };

  const columns = [
    { key: "name", label: "Merchant", render: (v: unknown, row: Merchant) => (
      <button type="button" onClick={() => openDetail(row.id)} className="font-medium text-white hover:text-blue-300">
        {String(v)}
      </button>
    ) },
    { key: "domain", label: "Domain", render: (v: unknown) => <span className="text-slate-400">{v ? String(v) : "—"}</span> },
    { key: "partner_type", label: "Partner Type", render: (v: unknown) => <span className="text-slate-300">{v ? String(v).replace(/_/g, " ") : "—"}</span> },
    { key: "commission_rate_pct", label: "Commission", render: (v: unknown) => <span className="text-slate-300">{v != null ? `${v}%` : "—"}</span> },
    {
      key: "onboarding_status",
      label: "Onboarding",
      render: (v: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${onboardingStatusStyles[String(v)] || "bg-slate-500/20 text-slate-400"}`}>
          {String(v).replace(/_/g, " ")}
        </span>
      ),
    },
    {
      key: "status",
      label: "Status",
      render: (v: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${v === "active" ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"}`}>
          {String(v)}
        </span>
      ),
    },
    { key: "product_count", label: "Products", render: (v: unknown) => <span className="text-slate-300">{String(v)}</span> },
    {
      key: "id",
      label: "",
      render: (_id: unknown, row: Merchant) => (
        <button
          type="button"
          onClick={() => handleToggleStatus(row)}
          className="rounded-full px-3 py-1.5 text-xs font-semibold text-slate-400 hover:bg-white/10 hover:text-white"
        >
          {row.status === "active" ? "Suspend" : "Reactivate"}
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <DataTable columns={columns} data={merchants} keyField="id" loading={loading} error={error} onRetry={fetchMerchants} />
      <p className="text-sm text-slate-400">
        Showing <span className="font-semibold text-white">{merchants.length}</span> of{" "}
        <span className="font-semibold text-white">{total}</span> merchants
      </p>

      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setSelected(null)}>
          <div className="glass-panel max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-[2rem] p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-blue-400" />
              <h3 className="text-lg font-semibold text-white">{selected.name}</h3>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-slate-400 sm:grid-cols-3">
              <p>Orders: <span className="text-white">{selected.order_count}</span></p>
              <p>GMV: <span className="text-white">PKR {selected.total_gmv.toLocaleString()}</span></p>
              <p>Products: <span className="text-white">{selected.product_count}</span></p>
            </div>

            <form onSubmit={handleSaveTerms} className="mt-4 space-y-3 rounded-xl bg-white/5 p-4">
              <h4 className="text-sm font-semibold text-white">Partnership terms</h4>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs text-slate-400">Partner type</label>
                  <select
                    aria-label="Partner type"
                    value={termsForm.partner_type}
                    onChange={(e) => setTermsForm({ ...termsForm, partner_type: e.target.value })}
                    className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none"
                  >
                    <option value="direct_integration">Direct integration</option>
                    <option value="affiliate">Affiliate</option>
                    <option value="scraped_only">Scraped only</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-400">Commission rate (%)</label>
                  <input
                    required
                    type="number"
                    step="0.01"
                    value={termsForm.commission_rate_pct}
                    onChange={(e) => setTermsForm({ ...termsForm, commission_rate_pct: e.target.value })}
                    className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-400">Payment terms (days)</label>
                  <input
                    required
                    type="number"
                    value={termsForm.payment_terms_days}
                    onChange={(e) => setTermsForm({ ...termsForm, payment_terms_days: e.target.value })}
                    className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-400">Min volume commitment (PKR)</label>
                  <input
                    type="number"
                    value={termsForm.min_volume_commitment_pkr}
                    onChange={(e) => setTermsForm({ ...termsForm, min_volume_commitment_pkr: e.target.value })}
                    className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none"
                  />
                </div>
              </div>
              <button type="submit" disabled={busy} className="rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60">
                Save terms
              </button>
            </form>

            <div className="mt-4 rounded-xl bg-white/5 p-4">
              <div className="flex items-center gap-2">
                <Wallet className="h-4 w-4 text-emerald-400" />
                <h4 className="text-sm font-semibold text-white">Commission &amp; payouts</h4>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-3 text-sm">
                <p className="text-slate-400">Accrued: <span className="text-white">PKR {(commission?.accrued ?? 0).toLocaleString()}</span></p>
                <p className="text-slate-400">Paid out: <span className="text-white">PKR {(commission?.paid_out ?? 0).toLocaleString()}</span></p>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={handleInitiatePayout}
                className="mt-3 rounded-full bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
              >
                Initiate payout
              </button>
            </div>

            <button type="button" onClick={() => setSelected(null)} className="mt-4 rounded-full px-4 py-2 text-sm font-semibold text-slate-400 hover:text-white">
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function OnboardingTab() {
  const [applications, setApplications] = useState<OnboardingApplication[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ merchant_name: "", domain: "", contact_name: "", contact_email: "", proposed_partner_type: "direct_integration", proposed_commission_rate_pct: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchApplications = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.get<{ items: OnboardingApplication[] }>("/admin/partners/onboarding-applications");
      setApplications(r.items);
      setError(null);
    } catch (err) {
      setApplications([]);
      setError(toErrorMessage(err, "Failed to load onboarding applications."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchApplications();
  }, [fetchApplications]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await adminApi.post("/admin/partners/onboarding-applications", {
        ...form,
        proposed_commission_rate_pct: form.proposed_commission_rate_pct ? Number(form.proposed_commission_rate_pct) : undefined,
      });
      setForm({ merchant_name: "", domain: "", contact_name: "", contact_email: "", proposed_partner_type: "direct_integration", proposed_commission_rate_pct: "" });
      setShowForm(false);
      await fetchApplications();
    } finally {
      setSubmitting(false);
    }
  };

  const handleDecision = async (id: number, decision: "approved" | "rejected") => {
    if (!confirm(`${decision === "approved" ? "Approve" : "Reject"} this application?`)) return;
    await adminApi.post(`/admin/partners/onboarding-applications/${id}/decision`, { decision });
    await fetchApplications();
  };

  const columns = [
    { key: "merchant_name", label: "Merchant", render: (v: unknown) => <span className="font-medium text-white">{String(v)}</span> },
    { key: "contact_email", label: "Contact", render: (v: unknown) => <span className="text-slate-400">{v ? String(v) : "—"}</span> },
    { key: "proposed_partner_type", label: "Proposed Type", render: (v: unknown) => <span className="text-slate-300">{v ? String(v).replace(/_/g, " ") : "—"}</span> },
    { key: "proposed_commission_rate_pct", label: "Proposed Rate", render: (v: unknown) => <span className="text-slate-300">{v != null ? `${v}%` : "—"}</span> },
    {
      key: "status",
      label: "Status",
      render: (v: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${onboardingStatusStyles[String(v)] || "bg-slate-500/20 text-slate-400"}`}>
          {String(v)}
        </span>
      ),
    },
    {
      key: "id",
      label: "Actions",
      render: (id: unknown, row: OnboardingApplication) => (
        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={row.status !== "pending" && row.status !== "in_review"}
            onClick={() => handleDecision(Number(id), "approved")}
            className="rounded-lg p-2 text-slate-400 hover:bg-emerald-500/10 hover:text-emerald-400 disabled:opacity-30"
            title="Approve"
          >
            <CheckCircle className="h-4 w-4" />
          </button>
          <button
            type="button"
            disabled={row.status !== "pending" && row.status !== "in_review"}
            onClick={() => handleDecision(Number(id), "rejected")}
            className="rounded-lg p-2 text-slate-400 hover:bg-rose-500/10 hover:text-rose-400 disabled:opacity-30"
            title="Reject"
          >
            <XCircle className="h-4 w-4" />
          </button>
        </div>
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
          New application
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="glass-panel space-y-4 rounded-[2rem] p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Merchant name</label>
              <input required value={form.merchant_name} onChange={(e) => setForm({ ...form, merchant_name: e.target.value })} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Domain</label>
              <input value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} placeholder="example.pk" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Contact name</label>
              <input value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Contact email</label>
              <input type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Proposed partner type</label>
              <select
                aria-label="Proposed partner type"
                value={form.proposed_partner_type}
                onChange={(e) => setForm({ ...form, proposed_partner_type: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none"
              >
                <option value="direct_integration">Direct integration</option>
                <option value="affiliate">Affiliate</option>
                <option value="scraped_only">Scraped only</option>
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Proposed commission (%)</label>
              <input type="number" step="0.01" value={form.proposed_commission_rate_pct} onChange={(e) => setForm({ ...form, proposed_commission_rate_pct: e.target.value })} className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none" />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={submitting} className="rounded-full bg-amber-400 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-amber-300 disabled:opacity-60">
              {submitting ? "Submitting..." : "Submit application"}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className="rounded-full px-5 py-2.5 text-sm font-semibold text-slate-400 hover:text-white">
              Cancel
            </button>
          </div>
        </form>
      )}

      <DataTable columns={columns} data={applications} keyField="id" loading={loading} error={error} onRetry={fetchApplications} />
    </div>
  );
}
