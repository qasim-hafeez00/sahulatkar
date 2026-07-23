"use client";

import { AlertCircle, AlertOctagon, CalendarClock, CheckCircle, FileText, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable } from "@/components/admin/data-table";
import { ErrorBanner, toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface AuditEntry {
  id: number;
  admin_user_id: number | null;
  customer_user_id: number | null;
  module: string;
  action: string;
  target_id: number | null;
  ip_address: string | null;
  created_at: string;
}

interface AuditTrailResponse {
  items: AuditEntry[];
  pagination: { page: number; limit: number };
}

interface ShariahAuditSummary {
  allocations_count: number;
  total_late_fee_allocated: number;
  contract_sequence_violations: number;
  compliance_status: string;
}

interface CharityAuditItem {
  id: number;
  loan_id: number;
  late_fee_amount: number;
  allocated_at: string;
  disbursed_at: string | null;
  disbursement_ref: string | null;
  charity_name: string | null;
}

interface CriticalAction {
  id: number;
  admin_user_id: number | null;
  module: string;
  action: string;
  target_id: number | null;
  created_at: string;
}

interface RegulatoryCalendarEntry {
  report_type: string;
  cadence_days: number;
  last_filed_at: string | null;
  last_reference_number: string | null;
  next_due_at: string;
  status: "upcoming" | "overdue";
}

interface DataPrivacyPanel {
  deletion_requests_by_status: Record<string, number>;
  recent_deletion_requests: { id: number; user_id: number; request_type: string; status: string; created_at: string }[];
}

export default function CompliancePage() {
  const [audits, setAudits] = useState<AuditEntry[]>([]);
  const [shariah, setShariah] = useState<ShariahAuditSummary | null>(null);
  const [charityAudits, setCharityAudits] = useState<CharityAuditItem[]>([]);
  const [criticalActions, setCriticalActions] = useState<CriticalAction[]>([]);
  const [calendar, setCalendar] = useState<RegulatoryCalendarEntry[]>([]);
  const [privacy, setPrivacy] = useState<DataPrivacyPanel | null>(null);
  const [moduleFilter, setModuleFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAudits = useCallback(async () => {
    const query = moduleFilter ? `?module=${moduleFilter}&limit=100` : "?limit=100";
    const response = await adminApi.get<AuditTrailResponse>(`/admin/audit-trail${query}`);
    setAudits(response.items);
  }, [moduleFilter]);

  const fetchAll = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetchAudits(),
      adminApi.get<ShariahAuditSummary>("/admin/compliance/shariah-audit").then(setShariah),
      adminApi.get<{ items: CharityAuditItem[] }>("/admin/compliance/charity-audit?limit=25").then((r) => setCharityAudits(r.items)),
      adminApi.get<{ items: CriticalAction[] }>("/admin/compliance/critical-actions?limit=15").then((r) => setCriticalActions(r.items)),
      adminApi.get<{ calendar: RegulatoryCalendarEntry[] }>("/admin/compliance/regulatory-calendar").then((r) => setCalendar(r.calendar)),
      adminApi.get<DataPrivacyPanel>("/admin/compliance/data-privacy").then(setPrivacy),
    ])
      .then(() => setError(null))
      .catch((err) => setError(toErrorMessage(err, "Failed to load compliance data.")))
      .finally(() => setLoading(false));
  }, [fetchAudits]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const columns = [
    {
      key: "created_at",
      label: "Time",
      render: (v: unknown) => <span className="text-slate-400">{new Date(String(v)).toLocaleString()}</span>,
    },
    { key: "module", label: "Module", render: (v: unknown) => <span className="text-white">{String(v)}</span> },
    { key: "action", label: "Action", render: (v: unknown) => <span className="text-slate-300">{String(v).replace(/_/g, " ")}</span> },
    { key: "admin_user_id", label: "Admin", render: (v: unknown) => <span className="text-slate-400">{v ? `#${v}` : "—"}</span> },
    { key: "target_id", label: "Target", render: (v: unknown) => <span className="text-slate-400">{v ? `#${v}` : "—"}</span> },
    { key: "ip_address", label: "IP", render: (v: unknown) => <span className="font-mono text-xs text-slate-500">{String(v ?? "—")}</span> },
  ];

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-18 / AD-19</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Compliance & audit</h2>
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={fetchAll} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <CheckCircle className={`h-4 w-4 ${shariah?.compliance_status === "compliant" ? "text-emerald-500" : "text-amber-500"}`} />
            Shariah Compliance
          </div>
          <p className="mt-2 text-2xl font-bold text-white">
            {shariah?.compliance_status === "compliant" ? "Compliant" : shariah ? "Violations found" : "—"}
          </p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <AlertCircle className="h-4 w-4 text-amber-500" />
            Contract Sequence Violations
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{shariah?.contract_sequence_violations ?? "—"}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <FileText className="h-4 w-4 text-blue-500" />
            Charity Allocations
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{shariah?.allocations_count ?? "—"}</p>
        </div>
      </div>

      <section className="glass-panel rounded-[2rem] p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          <h3 className="text-lg font-semibold text-white">Audit trail</h3>
          <select
            aria-label="Filter by module"
            value={moduleFilter}
            onChange={(e) => setModuleFilter(e.target.value)}
            className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white outline-none focus:border-amber-400/60"
          >
            <option value="">All modules</option>
            <option value="risk_blacklist">Risk blacklist</option>
            <option value="admin_support">Support</option>
            <option value="system">System</option>
          </select>
        </div>
        <DataTable columns={columns} data={audits} keyField="id" loading={loading} />
      </section>

      <section className="glass-panel rounded-[2rem] p-5">
        <h3 className="text-lg font-semibold text-white">Recent charity disbursements</h3>
        {charityAudits.length > 0 ? (
          <div className="mt-4 space-y-2 text-sm">
            {charityAudits.map((c) => (
              <div key={c.id} className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3">
                <div>
                  <p className="font-medium text-white">{c.charity_name ?? "Unassigned"}</p>
                  <p className="text-xs text-slate-500">Loan #{c.loan_id} · {new Date(c.allocated_at).toLocaleDateString()}</p>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-white">PKR {c.late_fee_amount.toLocaleString()}</p>
                  <p className={`text-xs ${c.disbursed_at ? "text-emerald-400" : "text-amber-400"}`}>
                    {c.disbursed_at ? "Disbursed" : "Pending"}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-sm text-slate-500">No charity allocations recorded yet.</p>
        )}
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="glass-panel rounded-[2rem] p-5">
          <div className="mb-4 flex items-center gap-2">
            <AlertOctagon className="h-5 w-5 text-rose-400" />
            <h3 className="text-lg font-semibold text-white">Critical action feed</h3>
          </div>
          {criticalActions.length > 0 ? (
            <div className="space-y-2 text-sm">
              {criticalActions.map((c) => (
                <div key={c.id} className="rounded-xl bg-white/5 px-4 py-3">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-white">{c.module}.{c.action.replace(/_/g, " ")}</span>
                    <span className="text-xs text-slate-500">{new Date(c.created_at).toLocaleString()}</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    Admin #{c.admin_user_id ?? "—"} {c.target_id ? `· Target #${c.target_id}` : ""}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">No critical (destructive) admin actions recorded yet.</p>
          )}
        </section>

        <section className="glass-panel rounded-[2rem] p-5">
          <div className="mb-4 flex items-center gap-2">
            <CalendarClock className="h-5 w-5 text-blue-400" />
            <h3 className="text-lg font-semibold text-white">Regulatory calendar</h3>
          </div>
          <div className="space-y-2 text-sm">
            {calendar.map((c) => (
              <div key={c.report_type} className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3">
                <div>
                  <p className="font-medium text-white">{c.report_type.replace(/_/g, " ").toUpperCase()}</p>
                  <p className="text-xs text-slate-500">
                    {c.last_filed_at ? `Last filed ${new Date(c.last_filed_at).toLocaleDateString()}` : "Never filed"}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-white">{new Date(c.next_due_at).toLocaleDateString()}</p>
                  <p className={`text-xs font-semibold ${c.status === "overdue" ? "text-rose-400" : "text-emerald-400"}`}>
                    {c.status}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="glass-panel rounded-[2rem] p-5">
        <div className="mb-4 flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-purple-400" />
          <h3 className="text-lg font-semibold text-white">Data privacy &amp; erasure requests</h3>
        </div>
        <div className="mb-4 flex flex-wrap gap-3">
          {Object.entries(privacy?.deletion_requests_by_status ?? {}).map(([status, count]) => (
            <div key={status} className="rounded-xl bg-white/5 px-4 py-2 text-sm">
              <span className="text-slate-400">{status}: </span>
              <span className="font-semibold text-white">{count}</span>
            </div>
          ))}
        </div>
        {privacy && privacy.recent_deletion_requests.length > 0 ? (
          <div className="space-y-2 text-sm">
            {privacy.recent_deletion_requests.map((r) => (
              <div key={r.id} className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3">
                <span className="text-white">User #{r.user_id} · {r.request_type}</span>
                <span className="text-slate-400">{r.status} · {new Date(r.created_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-500">No data erasure requests recorded yet.</p>
        )}
      </section>
    </section>
  );
}
