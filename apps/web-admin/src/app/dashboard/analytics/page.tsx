"use client";

import { BarChart3, Download, Globe2, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart as ReBarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ErrorBanner, toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface GmvTrendResponse {
  series: { date: string; gmv: number }[];
}
interface FunnelResponse {
  steps: Record<string, number>;
}
interface CreditBandResponse {
  bands: Record<string, number>;
}
interface DefaultRateResponse {
  series: { week: string; default_rate_pct: number }[];
}
interface CohortResponse {
  cohorts: { cohort: string; size: number; retention_m1: number }[];
}
interface ExecutiveSummaryResponse {
  gmv: number;
  gmv_growth_pct: number | null;
  orders_count: number;
  orders_growth_pct: number | null;
  new_users: number;
  active_users: number;
  approval_rate_pct: number | null;
  default_rate_pct: number | null;
  nps: number | null;
  nps_note: string;
}
interface GeographicResponse {
  provinces: { province: string; user_count: number; order_count: number; gmv: number }[];
}

const bandPalette = ["#21c97a", "#f5b301", "#6ea8fe", "#f85f73", "#a78bfa"];

function Panel({ title, description, children, action }: { title: string; description: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="glass-panel rounded-[2rem] p-5">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">{title}</h2>
          <p className="mt-1 text-sm text-slate-400">{description}</p>
        </div>
        {action}
      </div>
      <div className="h-72">{children}</div>
    </section>
  );
}

export default function AnalyticsPage() {
  const [gmv, setGmv] = useState<GmvTrendResponse | null>(null);
  const [funnel, setFunnel] = useState<FunnelResponse | null>(null);
  const [bands, setBands] = useState<CreditBandResponse | null>(null);
  const [defaultRate, setDefaultRate] = useState<DefaultRateResponse | null>(null);
  const [cohorts, setCohorts] = useState<CohortResponse | null>(null);
  const [executive, setExecutive] = useState<ExecutiveSummaryResponse | null>(null);
  const [geographic, setGeographic] = useState<GeographicResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(() => {
    setLoading(true);
    Promise.all([
      adminApi.get<GmvTrendResponse>("/admin/analytics/gmv-trend?period=30d"),
      adminApi.get<FunnelResponse>("/admin/analytics/approval-funnel?period=30d"),
      adminApi.get<CreditBandResponse>("/admin/analytics/credit-band-distribution"),
      adminApi.get<DefaultRateResponse>("/admin/analytics/default-rate-trend?period=90d"),
      adminApi.get<CohortResponse>("/admin/analytics/cohort"),
      adminApi.get<ExecutiveSummaryResponse>("/admin/analytics/executive-summary?period=30d"),
      adminApi.get<GeographicResponse>("/admin/analytics/geographic"),
    ])
      .then(([g, f, b, d, c, ex, geo]) => {
        setGmv(g);
        setFunnel(f);
        setBands(b);
        setDefaultRate(d);
        setCohorts(c);
        setExecutive(ex);
        setGeographic(geo);
        setError(null);
      })
      .catch((err) => setError(toErrorMessage(err, "Failed to load analytics data.")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const response = await fetch("/api/gateway/admin/analytics/export?report_type=gmv&period=30d");
      if (!response.ok) {
        setError(`Failed to export GMV report (${response.status}).`);
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "gmv_export.csv";
      a.click();
      URL.revokeObjectURL(url);
      setError(null);
    } catch (err) {
      setError(toErrorMessage(err, "Failed to export GMV report."));
    } finally {
      setExporting(false);
    }
  };

  const funnelData = funnel ? Object.entries(funnel.steps).map(([stage, count]) => ({ stage, count })) : [];
  const bandData = bands ? Object.entries(bands.bands).map(([band, count]) => ({ band, count })) : [];
  const totalOrders30d = funnelData.reduce((sum, f) => sum + f.count, 0);
  const avgDefaultRate =
    defaultRate && defaultRate.series.length > 0
      ? (defaultRate.series.reduce((s, r) => s + r.default_rate_pct, 0) / defaultRate.series.length).toFixed(2)
      : "0.00";
  const latestCohortRetention = cohorts?.cohorts[0] ? (cohorts.cohorts[0].retention_m1 * 100).toFixed(1) : "0.0";

  if (loading) {
    return (
      <section className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-900/50" />
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-20 / AD-21 / AD-22</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Analytics & insights</h2>
        </div>
        <button
          type="button"
          onClick={handleExport}
          disabled={exporting}
          className="flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm font-semibold text-white transition hover:bg-white/20 disabled:opacity-60"
        >
          <Download className="h-4 w-4" />
          {exporting ? "Exporting..." : "Export GMV (CSV)"}
        </button>
      </div>

      {error && <ErrorBanner message={error} onRetry={fetchAll} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <TrendingUp className="h-4 w-4 text-emerald-500" />
            Orders (30d)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{totalOrders30d.toLocaleString()}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <BarChart3 className="h-4 w-4 text-blue-500" />
            Avg Default Rate (90d)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{avgDefaultRate}%</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <TrendingUp className="h-4 w-4 text-purple-500" />
            Latest Cohort M1 Retention
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{latestCohortRetention}%</p>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="GMV Trend" description="Daily gross merchandise value, last 30 days.">
          {gmv && gmv.series.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={gmv.series}>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                <XAxis dataKey="date" stroke="#94a3b8" tickLine={false} axisLine={false} />
                <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
                <Line type="monotone" dataKey="gmv" stroke="#f5b301" strokeWidth={3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-500">No data</div>
          )}
        </Panel>

        <Panel title="Order Funnel" description="Order counts by status, last 30 days.">
          {funnelData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <ReBarChart data={funnelData} layout="vertical">
                <CartesianGrid stroke="rgba(255,255,255,0.06)" horizontal={false} />
                <XAxis type="number" stroke="#94a3b8" tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="stage" stroke="#94a3b8" tickLine={false} axisLine={false} width={100} />
                <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
                <Bar dataKey="count" radius={[0, 12, 12, 0]} fill="#21c97a" />
              </ReBarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-500">No data</div>
          )}
        </Panel>

        <Panel title="Credit Band Distribution" description="Risk assessment bands, last 90 days.">
          {bandData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={bandData} dataKey="count" nameKey="band" innerRadius={56} outerRadius={92} paddingAngle={4}>
                  {bandData.map((entry, index) => (
                    <Cell key={entry.band} fill={bandPalette[index % bandPalette.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-500">No data</div>
          )}
        </Panel>

        <Panel title="Default Rate Trend" description="Weekly overdue installment rate, last 90 days.">
          {defaultRate && defaultRate.series.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={defaultRate.series}>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                <XAxis dataKey="week" stroke="#94a3b8" tickLine={false} axisLine={false} />
                <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
                <Area type="monotone" dataKey="default_rate_pct" stroke="#f85f73" fill="rgba(248,95,115,0.18)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-500">No data</div>
          )}
        </Panel>
      </div>

      <section className="glass-panel rounded-[2rem] p-5">
        <h2 className="text-lg font-semibold text-white">Monthly Cohorts</h2>
        <p className="mt-1 text-sm text-slate-400">User acquisition cohorts with 30-day retention.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-4 py-2">Cohort</th>
                <th className="px-4 py-2">Size</th>
                <th className="px-4 py-2">M1 Retention</th>
              </tr>
            </thead>
            <tbody>
              {(cohorts?.cohorts ?? []).map((c) => (
                <tr key={c.cohort} className="border-b border-white/5">
                  <td className="px-4 py-2 text-white">{c.cohort}</td>
                  <td className="px-4 py-2 text-slate-300">{c.size}</td>
                  <td className="px-4 py-2 text-slate-300">{(c.retention_m1 * 100).toFixed(1)}%</td>
                </tr>
              ))}
              {(!cohorts || cohorts.cohorts.length === 0) && (
                <tr>
                  <td colSpan={3} className="px-4 py-6 text-center text-slate-500">
                    No cohort data available
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="glass-panel rounded-[2rem] p-5">
        <h2 className="text-lg font-semibold text-white">Executive Summary</h2>
        <p className="mt-1 text-sm text-slate-400">High-level KPIs for leadership review, last 30 days.</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl bg-white/5 px-4 py-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">GMV</p>
            <p className="mt-1 text-lg font-semibold text-white">PKR {(executive?.gmv ?? 0).toLocaleString()}</p>
            {executive?.gmv_growth_pct != null && (
              <p className={executive.gmv_growth_pct >= 0 ? "text-xs text-emerald-400" : "text-xs text-rose-400"}>
                {executive.gmv_growth_pct >= 0 ? "+" : ""}{executive.gmv_growth_pct}% vs prior period
              </p>
            )}
          </div>
          <div className="rounded-xl bg-white/5 px-4 py-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">New Users</p>
            <p className="mt-1 text-lg font-semibold text-white">{executive?.new_users ?? 0}</p>
          </div>
          <div className="rounded-xl bg-white/5 px-4 py-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Approval Rate</p>
            <p className="mt-1 text-lg font-semibold text-white">
              {executive?.approval_rate_pct != null ? `${executive.approval_rate_pct}%` : "—"}
            </p>
          </div>
          <div className="rounded-xl bg-white/5 px-4 py-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">NPS</p>
            <p className="mt-1 text-lg font-semibold text-white">N/A</p>
            <p className="text-xs text-slate-500">{executive?.nps_note}</p>
          </div>
        </div>
      </section>

      <section className="glass-panel rounded-[2rem] p-5">
        <div className="mb-4 flex items-center gap-2">
          <Globe2 className="h-5 w-5 text-blue-400" />
          <h2 className="text-lg font-semibold text-white">Geographic distribution</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-4 py-2">Province</th>
                <th className="px-4 py-2">Users</th>
                <th className="px-4 py-2">Orders</th>
                <th className="px-4 py-2">GMV</th>
              </tr>
            </thead>
            <tbody>
              {(geographic?.provinces ?? []).map((p) => (
                <tr key={p.province} className="border-b border-white/5">
                  <td className="px-4 py-2 text-white">{p.province}</td>
                  <td className="px-4 py-2 text-slate-300">{p.user_count.toLocaleString()}</td>
                  <td className="px-4 py-2 text-slate-300">{p.order_count.toLocaleString()}</td>
                  <td className="px-4 py-2 text-slate-300">PKR {p.gmv.toLocaleString()}</td>
                </tr>
              ))}
              {(!geographic || geographic.provinces.length === 0) && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-slate-500">
                    No geographic data available
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
