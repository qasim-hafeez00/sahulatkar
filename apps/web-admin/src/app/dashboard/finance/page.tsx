"use client";

import { AlertOctagon, CheckCircle, DollarSign, FileText, HeartHandshake, ScaleIcon, TrendingDown } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ErrorBanner, toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface FinancialSummary {
  total_payments: number;
  transactions_count: number;
}

interface ReconciliationSummary {
  total_transactions: number;
  reconciled_transactions: number;
  unreconciled_transactions: number;
}

interface ShariahAuditSummary {
  allocations_count: number;
  total_late_fee_allocated: number;
  total_disbursed: number;
  contract_sequence_violations: number;
  compliance_status: string;
}

interface CharityReportItem {
  charity_name: string;
  allocations_count: number;
  allocated_amount: number;
  disbursed_amount: number;
}

interface PnlResponse {
  series: { month: string; gmv: number; platform_profit: number; product_cost: number; net_margin: number }[];
  totals: {
    gmv: number;
    platform_profit: number;
    product_cost: number;
    late_fee_income: number;
    charity_allocated: number;
    net_income: number;
  };
}

interface CreditLossResponse {
  defaulted_count: number;
  defaulted_outstanding: number;
  written_off_count: number;
  written_off_amount: number;
  active_count: number;
  active_outstanding: number;
  provision_rate_pct: number;
  provision_estimate: number;
  default_rate_pct: number;
}

interface TaxSummaryResponse {
  period_months: number;
  taxable_income: number;
  gst_rate_pct: number;
  gst_liability: number;
}

function formatPkr(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `PKR ${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `PKR ${(value / 1_000).toFixed(1)}K`;
  return `PKR ${value.toFixed(0)}`;
}

export default function FinancePage() {
  const [summary, setSummary] = useState<FinancialSummary | null>(null);
  const [reconciliation, setReconciliation] = useState<ReconciliationSummary | null>(null);
  const [shariah, setShariah] = useState<ShariahAuditSummary | null>(null);
  const [charities, setCharities] = useState<CharityReportItem[]>([]);
  const [pnl, setPnl] = useState<PnlResponse | null>(null);
  const [creditLoss, setCreditLoss] = useState<CreditLossResponse | null>(null);
  const [taxSummary, setTaxSummary] = useState<TaxSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [filing, setFiling] = useState(false);
  const [filingResult, setFilingResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(() => {
    setLoading(true);
    Promise.all([
      adminApi.get<FinancialSummary>("/admin/compliance/financial-summary"),
      adminApi.get<ReconciliationSummary>("/admin/compliance/reconciliation"),
      adminApi.get<ShariahAuditSummary>("/admin/compliance/shariah-audit"),
      adminApi.get<{ items: CharityReportItem[] }>("/admin/compliance/charity-report"),
      adminApi.get<PnlResponse>("/admin/finance/pnl?months=6"),
      adminApi.get<CreditLossResponse>("/admin/finance/credit-loss"),
      adminApi.get<TaxSummaryResponse>("/admin/finance/tax-summary?months=1"),
    ])
      .then(([s, r, sh, c, p, cl, tx]) => {
        setSummary(s);
        setReconciliation(r);
        setShariah(sh);
        setCharities(c.items);
        setPnl(p);
        setCreditLoss(cl);
        setTaxSummary(tx);
        setError(null);
      })
      .catch((err) => setError(toErrorMessage(err, "Failed to load finance data.")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleGenerateFiling = async () => {
    setFiling(true);
    setFilingResult(null);
    try {
      const result = await adminApi.post<{ reference_number: string }>("/admin/finance/tax-summary/generate?months=1");
      setFilingResult(result.reference_number);
    } finally {
      setFiling(false);
    }
  };

  const reconciledPct =
    reconciliation && reconciliation.total_transactions > 0
      ? ((reconciliation.reconciled_transactions / reconciliation.total_transactions) * 100).toFixed(1)
      : "0.0";

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-13 / AD-14 / AD-15</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Finance & reporting</h2>
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={fetchAll} />}

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-900/50" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <div className="glass-panel rounded-xl p-4">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <DollarSign className="h-4 w-4 text-emerald-500" />
                Total Payments
              </div>
              <p className="mt-2 text-2xl font-bold text-white">{summary ? formatPkr(summary.total_payments) : "—"}</p>
              <p className="mt-1 text-xs text-slate-500">{summary?.transactions_count.toLocaleString()} transactions</p>
            </div>
            <div className="glass-panel rounded-xl p-4">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <ScaleIcon className="h-4 w-4 text-blue-500" />
                Reconciled
              </div>
              <p className="mt-2 text-2xl font-bold text-white">{reconciledPct}%</p>
              <p className="mt-1 text-xs text-slate-500">
                {reconciliation?.reconciled_transactions.toLocaleString()} of {reconciliation?.total_transactions.toLocaleString()}
              </p>
            </div>
            <div className="glass-panel rounded-xl p-4">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <CheckCircle className={`h-4 w-4 ${shariah?.compliance_status === "compliant" ? "text-emerald-500" : "text-amber-500"}`} />
                Shariah Compliance
              </div>
              <p className="mt-2 text-2xl font-bold text-white">
                {shariah?.compliance_status === "compliant" ? "Compliant" : "Violations found"}
              </p>
              <p className="mt-1 text-xs text-slate-500">{shariah?.contract_sequence_violations ?? 0} sequence violations</p>
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <section className="glass-panel rounded-[2rem] p-5">
              <h3 className="text-lg font-semibold text-white">Reconciliation breakdown</h3>
              <div className="mt-4 space-y-2 text-sm">
                <div className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3">
                  <span className="text-slate-400">Reconciled</span>
                  <span className="font-semibold text-emerald-300">{reconciliation?.reconciled_transactions.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3">
                  <span className="text-slate-400">Unreconciled</span>
                  <span className="font-semibold text-amber-300">{reconciliation?.unreconciled_transactions.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3">
                  <span className="text-slate-400">Total</span>
                  <span className="font-semibold text-white">{reconciliation?.total_transactions.toLocaleString()}</span>
                </div>
              </div>
            </section>

            <section className="glass-panel rounded-[2rem] p-5">
              <div className="mb-4 flex items-center gap-2">
                <HeartHandshake className="h-5 w-5 text-blue-400" />
                <h3 className="text-lg font-semibold text-white">Late-fee charity allocations</h3>
              </div>
              {charities.length > 0 ? (
                <div className="space-y-2 text-sm">
                  {charities.map((c) => (
                    <div key={c.charity_name} className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3">
                      <div>
                        <p className="font-medium text-white">{c.charity_name}</p>
                        <p className="text-xs text-slate-500">{c.allocations_count} allocations</p>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold text-white">{formatPkr(c.allocated_amount)}</p>
                        <p className="text-xs text-emerald-400">{formatPkr(c.disbursed_amount)} disbursed</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500">No charity allocations recorded yet.</p>
              )}
            </section>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="glass-panel rounded-xl p-4">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <DollarSign className="h-4 w-4 text-emerald-500" />
                Net Income (6mo)
              </div>
              <p className="mt-2 text-2xl font-bold text-white">{pnl ? formatPkr(pnl.totals.net_income) : "—"}</p>
            </div>
            <div className="glass-panel rounded-xl p-4">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <TrendingDown className="h-4 w-4 text-rose-500" />
                Default Rate
              </div>
              <p className="mt-2 text-2xl font-bold text-white">{creditLoss ? `${creditLoss.default_rate_pct}%` : "—"}</p>
            </div>
            <div className="glass-panel rounded-xl p-4">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <AlertOctagon className="h-4 w-4 text-amber-500" />
                Loss Provision Estimate
              </div>
              <p className="mt-2 text-2xl font-bold text-white">{creditLoss ? formatPkr(creditLoss.provision_estimate) : "—"}</p>
            </div>
            <div className="glass-panel rounded-xl p-4">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <FileText className="h-4 w-4 text-blue-500" />
                GST Liability (MTD)
              </div>
              <p className="mt-2 text-2xl font-bold text-white">{taxSummary ? formatPkr(taxSummary.gst_liability) : "—"}</p>
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <section className="glass-panel rounded-[2rem] p-5">
              <h3 className="text-lg font-semibold text-white">P&amp;L Trend</h3>
              <p className="mt-1 text-sm text-slate-400">Platform profit vs. product cost, last 6 months.</p>
              <div className="mt-4 h-64">
                {pnl && pnl.series.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={pnl.series}>
                      <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                      <XAxis dataKey="month" stroke="#94a3b8" tickLine={false} axisLine={false} />
                      <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
                      <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
                      <Bar dataKey="net_margin" name="Net margin" fill="#f5b301" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-slate-500">No revenue recorded in this period</div>
                )}
              </div>
            </section>

            <section className="glass-panel rounded-[2rem] p-5">
              <h3 className="text-lg font-semibold text-white">Credit loss &amp; tax filing</h3>
              <div className="mt-4 space-y-2 text-sm">
                <div className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3">
                  <span className="text-slate-400">Defaulted loans</span>
                  <span className="font-semibold text-rose-300">{creditLoss?.defaulted_count ?? 0}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3">
                  <span className="text-slate-400">Written off</span>
                  <span className="font-semibold text-amber-300">{creditLoss ? formatPkr(creditLoss.written_off_amount) : "—"}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3">
                  <span className="text-slate-400">Taxable income (MTD)</span>
                  <span className="font-semibold text-white">{taxSummary ? formatPkr(taxSummary.taxable_income) : "—"}</span>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-3">
                <button
                  type="button"
                  disabled={filing}
                  onClick={handleGenerateFiling}
                  className="rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-60"
                >
                  {filing ? "Filing..." : "Generate GST filing"}
                </button>
                {filingResult && <span className="text-sm text-emerald-300">Filed as {filingResult}</span>}
              </div>
            </section>
          </div>
        </>
      )}
    </section>
  );
}
