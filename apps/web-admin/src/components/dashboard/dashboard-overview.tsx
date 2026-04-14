"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type KpiCardProps = {
  label: string;
  value: string;
  delta: string;
  tone: "good" | "warn" | "bad";
  note: string;
};

const metricTone: Record<KpiCardProps["tone"], string> = {
  good: "from-emerald-400/20 to-emerald-400/5 text-emerald-200 border-emerald-400/20",
  warn: "from-amber-400/20 to-amber-400/5 text-amber-100 border-amber-400/20",
  bad: "from-rose-400/20 to-rose-400/5 text-rose-100 border-rose-400/20",
};

const kpis: KpiCardProps[] = [
  { label: "GMV", value: "PKR 24.5M", delta: "+23%", tone: "good", note: "30-day rolling volume" },
  { label: "Active Users", value: "12,458", delta: "+15%", tone: "good", note: "Users with recent orders" },
  { label: "Approval Rate", value: "76.3%", delta: "-2.1%", tone: "good", note: "Credit approvals" },
  { label: "Default Rate", value: "1.8%", delta: "-0.3%", tone: "warn", note: "60+ DPD share" },
  { label: "Orders Today", value: "347", delta: "+12%", tone: "good", note: "Same-day orders" },
  { label: "Overdue Amount", value: "PKR 145K", delta: "+8%", tone: "bad", note: "Past due balances" },
];

const gmvTrend = [
  { day: "Mon", value: 1.8 },
  { day: "Tue", value: 2.2 },
  { day: "Wed", value: 2.0 },
  { day: "Thu", value: 2.8 },
  { day: "Fri", value: 3.6 },
  { day: "Sat", value: 3.2 },
  { day: "Sun", value: 4.1 },
];

const orderFunnel = [
  { stage: "URL", count: 3500 },
  { stage: "Extracted", count: 3100 },
  { stage: "Offer", count: 2900 },
  { stage: "Contract", count: 2600 },
  { stage: "VCN", count: 2500 },
];

const revenueBreakdown = [
  { name: "Murabaha", value: 58 },
  { name: "Fees", value: 18 },
  { name: "Affiliate", value: 24 },
];

const paymentStatus = [
  { status: "Paid", value: 72 },
  { status: "Pending", value: 18 },
  { status: "Failed", value: 10 },
];

const acquisitionTrend = [
  { month: "Jan", value: 1200 },
  { month: "Feb", value: 1600 },
  { month: "Mar", value: 1900 },
  { month: "Apr", value: 2400 },
  { month: "May", value: 3100 },
  { month: "Jun", value: 3600 },
];

const revenuePalette = ["#f5b301", "#21c97a", "#6ea8fe"];

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
  return (
    <div className="space-y-6">
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {kpis.map((card) => (
          <KpiCard key={card.label} {...card} />
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <Panel title="GMV Trend" description="Rolling seven-day GMV movement in PKR millions.">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={gmvTrend}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="day" stroke="#94a3b8" tickLine={false} axisLine={false} />
              <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
              <Line type="monotone" dataKey="value" stroke="#f5b301" strokeWidth={3} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Order Funnel" description="Conversion throughput across the checkout lifecycle.">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={orderFunnel} layout="vertical">
              <CartesianGrid stroke="rgba(255,255,255,0.06)" horizontal={false} />
              <XAxis type="number" stroke="#94a3b8" tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="stage" stroke="#94a3b8" tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
              <Bar dataKey="count" radius={[0, 12, 12, 0]} fill="#21c97a" />
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Revenue Breakdown" description="Contribution mix across murabaha, fees, and affiliate revenue.">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={revenueBreakdown} dataKey="value" nameKey="name" innerRadius={56} outerRadius={92} paddingAngle={4}>
                {revenueBreakdown.map((entry, index) => (
                  <Cell key={entry.name} fill={revenuePalette[index % revenuePalette.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Payment Status" description="Current payment state distribution across due items.">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={paymentStatus}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="status" stroke="#94a3b8" tickLine={false} axisLine={false} />
              <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
              <Bar dataKey="value" radius={[12, 12, 0, 0]}>
                {paymentStatus.map((entry, index) => (
                  <Cell key={entry.status} fill={index === 0 ? "#21c97a" : index === 1 ? "#f5b301" : "#f85f73"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="User Acquisition" description="Monthly acquisition growth across the last six months.">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={acquisitionTrend}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="month" stroke="#94a3b8" tickLine={false} axisLine={false} />
              <YAxis stroke="#94a3b8" tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "#111a32", border: "1px solid rgba(255,255,255,0.08)" }} />
              <Area type="monotone" dataKey="value" stroke="#6ea8fe" fill="rgba(110,168,254,0.18)" />
            </AreaChart>
          </ResponsiveContainer>
        </Panel>
      </section>
    </div>
  );
}
