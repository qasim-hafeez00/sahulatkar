"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
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
import { adminApi } from "@/lib/api-client";

interface KpiValue {
  value: number;
  trend: string;
  status: "green" | "yellow" | "red";
}

interface DashboardSummary {
  kpis: {
    gmv: KpiValue;
    active_users: KpiValue;
    approval_rate: KpiValue;
    default_rate: KpiValue;
    orders_total: KpiValue;
    payments_due: KpiValue;
    overdue_amount: KpiValue;
  };
  action_items: { priority: string; type: string; count: number; action_button: string }[];
}

interface GmvTrendResponse {
  period: string;
  series: { date: string; gmv: number }[];
}

interface ApprovalFunnelResponse {
  period: string;
  steps: Record<string, number>;
}

interface RevenueBreakdownResponse {
  series: { month: string; platform_profit: number; product_cost: number; gmv: number }[];
}

interface PaymentStatusResponse {
  statuses: Record<string, { count: number; total_amount: number }>;
}

interface AcquisitionChannelResponse {
  channels: { channel: string; acquired_users: number; orders_generated: number }[];
}

const paymentStatusPalette = ["#21c97a", "#f5b301", "#6ea8fe", "#f85f73", "#a78bfa"];

type KpiCardProps = {
  label: string;
  value: string;
  delta: string;
  tone: "green" | "yellow" | "red";
  note: string;
};

const metricTone: Record<KpiCardProps["tone"], string> = {
  green: "from-emerald-400/20 to-emerald-400/5 text-emerald-200 border-emerald-400/20",
  yellow: "from-amber-400/20 to-amber-400/5 text-amber-100 border-amber-400/20",
  red: "from-rose-400/20 to-rose-400/5 text-rose-100 border-rose-400/20",
};

function formatPkr(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `PKR ${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `PKR ${(value / 1_000).toFixed(1)}K`;
  return `PKR ${value.toFixed(0)}`;
}

function KpiCard({ label, value, delta, tone, note }: KpiCardProps) {
  return (
    <div className={`rounded-[1.5rem] border bg-gradient-to-br p-5 ${metricTone[tone]}`}>
      <p className="text-xs uppercase tracking-[0.24em] text-current/70">{label}</p>
      <div className="mt-4 flex items-end justify-between gap-4">
        <p className="text-3xl font-semibold text-white">{value}</p>
        <span className="rounded-full border border-current/20 bg-white/10 px-3 py-1 text-xs font-semibold">
          {delta}
        </span>
      </div>
      <p className="mt-3 text-sm text-slate-300">{note}</p>
    </div>
  );
}

function Panel({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <section className="glass-panel rounded-[2rem] p-5">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        <p className="mt-1 text-sm text-slate-400">{description}</p>
      </div>
      <div className="h-72">{children}</div>
    </section>
  );
}

export function DashboardOverview() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [gmvTrend, setGmvTrend] = useState<GmvTrendResponse | null>(null);
  const [funnel, setFunnel] = useState<ApprovalFunnelResponse | null>(null);
  const [revenue, setRevenue] = useState<RevenueBreakdownResponse | null>(null);
  const [paymentStatus, setPaymentStatus] = useState<PaymentStatusResponse | null>(null);
  const [acquisition, setAcquisition] = useState<AcquisitionChannelResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      adminApi.get<DashboardSummary>("/admin/dashboard"),
      adminApi.get<GmvTrendResponse>("/admin/analytics/gmv-trend?period=30d"),
      adminApi.get<ApprovalFunnelResponse>("/admin/analytics/approval-funnel?period=30d"),
      adminApi.get<RevenueBreakdownResponse>("/admin/dashboard/revenue-breakdown?months=6"),
      adminApi.get<PaymentStatusResponse>("/admin/dashboard/payment-status-distribution?days=30"),
      adminApi.get<AcquisitionChannelResponse>("/admin/dashboard/acquisition-by-channel"),
    ])
      .then(([s, g, f, r, p, a]) => {
        setSummary(s);
        setGmvTrend(g);
        setFunnel(f);
        setRevenue(r);
        setPaymentStatus(p);
        setAcquisition(a);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-32 animate-pulse rounded-[1.5rem] bg-slate-900/50" />
          ))}
        </div>
      </div>
    );
  }

  const kpis = summary?.kpis;
  const cards: KpiCardProps[] = kpis
    ? [
        { label: "GMV", value: formatPkr(kpis.gmv.value), delta: kpis.gmv.trend, tone: kpis.gmv.status, note: "Total order volume" },
        { label: "Active Users", value: kpis.active_users.value.toLocaleString(), delta: kpis.active_users.trend, tone: kpis.active_users.status, note: "Users with active status" },
        { label: "Approval Rate", value: `${kpis.approval_rate.value}%`, delta: kpis.approval_rate.trend, tone: kpis.approval_rate.status, note: "Risk assessments, last 30 days" },
        { label: "Default Rate", value: `${kpis.default_rate.value}%`, delta: kpis.default_rate.trend, tone: kpis.default_rate.status, note: "Overdue vs finished installments" },
        { label: "Orders (active)", value: kpis.orders_total.value.toLocaleString(), delta: kpis.orders_total.trend, tone: kpis.orders_total.status, note: "Excludes cancelled/refunded" },
        { label: "Payments Due", value: kpis.payments_due.value.toLocaleString(), delta: kpis.payments_due.trend, tone: kpis.payments_due.status, note: "Pending installments" },
        { label: "Overdue Amount", value: formatPkr(kpis.overdue_amount.value), delta: kpis.overdue_amount.trend, tone: kpis.overdue_amount.status, note: "Past-due balances" },
      ]
    : [];

  const funnelData = funnel ? Object.entries(funnel.steps).map(([stage, count]) => ({ stage, count })) : [];
  const paymentStatusData = paymentStatus
    ? Object.entries(paymentStatus.statuses).map(([status, v]) => ({ status, count: v.count }))
    : [];

  return (
    <div className="space-y-6">
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map((card) => (
          <KpiCard key={card.label} {...card} />
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <Panel title="GMV Trend" description="Daily gross merchandise value, last 30 days.">
          {gmvTrend && gmvTrend.series.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={gmvTrend.series}>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                <XAxis dataKey="date" stroke="#94a3b8" tickLine={false} axisLine={false} />
                <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
                <Line type="monotone" dataKey="gmv" stroke="#f5b301" strokeWidth={3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-500">No orders in this period</div>
          )}
        </Panel>

        <Panel title="Order Status Distribution" description="Order counts by status, last 30 days.">
          {funnelData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={funnelData} layout="vertical">
                <CartesianGrid stroke="rgba(255,255,255,0.06)" horizontal={false} />
                <XAxis type="number" stroke="#94a3b8" tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="stage" stroke="#94a3b8" tickLine={false} axisLine={false} width={100} />
                <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
                <Bar dataKey="count" radius={[0, 12, 12, 0]} fill="#21c97a" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-500">No orders in this period</div>
          )}
        </Panel>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <Panel title="Revenue Breakdown" description="Platform profit vs. product cost, last 6 months.">
          {revenue && revenue.series.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={revenue.series}>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                <XAxis dataKey="month" stroke="#94a3b8" tickLine={false} axisLine={false} />
                <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
                <Bar dataKey="platform_profit" name="Platform profit" stackId="rev" fill="#f5b301" radius={[4, 4, 0, 0]} />
                <Bar dataKey="product_cost" name="Product cost" stackId="rev" fill="#6ea8fe" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-500">No revenue recorded in this period</div>
          )}
        </Panel>

        <Panel title="Payment Status Distribution" description="Transaction outcomes, last 30 days.">
          {paymentStatusData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={paymentStatusData} dataKey="count" nameKey="status" innerRadius={56} outerRadius={92} paddingAngle={4}>
                  {paymentStatusData.map((entry, index) => (
                    <Cell key={entry.status} fill={paymentStatusPalette[index % paymentStatusPalette.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-500">No transactions in this period</div>
          )}
        </Panel>
      </section>

      <section className="glass-panel rounded-[2rem] p-5">
        <h2 className="text-lg font-semibold text-white">Acquisition by Channel</h2>
        <p className="mt-1 text-sm text-slate-400">Where customers first came from, and how many went on to order.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-4 py-2">Channel</th>
                <th className="px-4 py-2">Acquired Users</th>
                <th className="px-4 py-2">Orders Generated</th>
              </tr>
            </thead>
            <tbody>
              {(acquisition?.channels ?? []).map((c) => (
                <tr key={c.channel} className="border-b border-white/5">
                  <td className="px-4 py-2 text-white">{c.channel}</td>
                  <td className="px-4 py-2 text-slate-300">{c.acquired_users.toLocaleString()}</td>
                  <td className="px-4 py-2 text-slate-300">{c.orders_generated.toLocaleString()}</td>
                </tr>
              ))}
              {(!acquisition || acquisition.channels.length === 0) && (
                <tr>
                  <td colSpan={3} className="px-4 py-6 text-center text-slate-500">
                    No acquisition attribution data recorded yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {summary?.action_items?.length ? (
        <section className="glass-panel rounded-[2rem] p-5">
          <h2 className="text-lg font-semibold text-white">Action Center</h2>
          <ul className="mt-4 space-y-2">
            {summary.action_items.map((item, i) => (
              <li key={i} className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3 text-sm text-slate-300">
                <span>{item.type.replace(/_/g, " ")}</span>
                <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-white">{item.count}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
