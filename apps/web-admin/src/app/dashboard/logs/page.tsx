"use client";

import { AlertTriangle, Clock, ListChecks } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable } from "@/components/admin/data-table";
import { ErrorBanner, toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface ErrorLog {
  id: number;
  error_id: string;
  service: string;
  severity: string;
  message: string;
  user_id: number | null;
  created_at: string;
}

interface BackgroundJob {
  id: number;
  job_id: string;
  queue_name: string;
  task_name: string;
  status: string;
  error_message: string | null;
  enqueued_at: string;
  finished_at: string | null;
}

interface ScheduledTask {
  id: number;
  task_name: string;
  schedule_cron: string;
  is_active: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: string | null;
}

const severityStyles: Record<string, string> = {
  info: "bg-blue-500/20 text-blue-400",
  warning: "bg-amber-500/20 text-amber-400",
  error: "bg-rose-500/20 text-rose-400",
  critical: "bg-rose-600/30 text-rose-300",
};

const jobStatusStyles: Record<string, string> = {
  queued: "bg-slate-500/20 text-slate-400",
  running: "bg-blue-500/20 text-blue-400",
  completed: "bg-emerald-500/20 text-emerald-400",
  failed: "bg-rose-500/20 text-rose-400",
  cancelled: "bg-slate-500/20 text-slate-400",
};

const TABS = [
  { key: "errors", label: "Error Logs" },
  { key: "jobs", label: "Background Jobs" },
  { key: "scheduled", label: "Scheduled Tasks" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function LogsPage() {
  const [tab, setTab] = useState<TabKey>("errors");
  const [summary, setSummary] = useState<{ errors_last_24h_by_severity: Record<string, number>; jobs_by_status: Record<string, number> } | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const fetchSummary = useCallback(() => {
    adminApi
      .get<{ errors_last_24h_by_severity: Record<string, number>; jobs_by_status: Record<string, number> }>("/admin/logs/summary")
      .then((r) => {
        setSummary(r);
        setSummaryError(null);
      })
      .catch((err) => setSummaryError(toErrorMessage(err, "Failed to load logs summary.")));
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [tab, fetchSummary]);

  const totalErrors24h = summary ? Object.values(summary.errors_last_24h_by_severity).reduce((a, b) => a + b, 0) : 0;
  const failedJobs = summary?.jobs_by_status.failed ?? 0;

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-33</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Logs &amp; audit trail</h2>
      </div>

      {summaryError && <ErrorBanner message={summaryError} onRetry={fetchSummary} />}

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <AlertTriangle className="h-4 w-4 text-rose-500" />
            Errors (24h)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{totalErrors24h}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <ListChecks className="h-4 w-4 text-amber-500" />
            Failed Jobs
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{failedJobs}</p>
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

      {tab === "errors" && <ErrorLogsTab />}
      {tab === "jobs" && <BackgroundJobsTab />}
      {tab === "scheduled" && <ScheduledTasksTab />}
    </section>
  );
}

function ErrorLogsTab() {
  const [logs, setLogs] = useState<ErrorLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.get<{ items: ErrorLog[]; pagination: { total: number } }>("/admin/logs/errors?limit=100");
      setLogs(r.items);
      setTotal(r.pagination.total);
      setError(null);
    } catch (err) {
      setLogs([]);
      setError(toErrorMessage(err, "Failed to load error logs."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const columns = [
    { key: "service", label: "Service", render: (v: unknown) => <span className="font-mono text-sm text-white">{String(v)}</span> },
    {
      key: "severity",
      label: "Severity",
      render: (v: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${severityStyles[String(v)] || ""}`}>{String(v)}</span>
      ),
    },
    { key: "message", label: "Message", render: (v: unknown) => <span className="text-slate-300 line-clamp-2">{String(v)}</span> },
    { key: "created_at", label: "Time", render: (v: unknown) => <span className="text-slate-400">{new Date(String(v)).toLocaleString()}</span> },
  ];

  return (
    <div className="space-y-4">
      <DataTable columns={columns} data={logs} keyField="id" loading={loading} error={error} onRetry={fetchLogs} />
      <p className="text-sm text-slate-400">
        Showing <span className="font-semibold text-white">{logs.length}</span> of{" "}
        <span className="font-semibold text-white">{total}</span> error logs
      </p>
    </div>
  );
}

function BackgroundJobsTab() {
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchJobs = useCallback(() => {
    setLoading(true);
    adminApi
      .get<{ items: BackgroundJob[] }>("/admin/logs/background-jobs?limit=100")
      .then((r) => {
        setJobs(r.items);
        setError(null);
      })
      .catch((err) => {
        setJobs([]);
        setError(toErrorMessage(err, "Failed to load background jobs."));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  const columns = [
    { key: "task_name", label: "Task", render: (v: unknown) => <span className="font-medium text-white">{String(v)}</span> },
    { key: "queue_name", label: "Queue", render: (v: unknown) => <span className="text-slate-400">{String(v)}</span> },
    {
      key: "status",
      label: "Status",
      render: (v: unknown) => (
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${jobStatusStyles[String(v)] || ""}`}>{String(v)}</span>
      ),
    },
    { key: "enqueued_at", label: "Enqueued", render: (v: unknown) => <span className="text-slate-400">{new Date(String(v)).toLocaleString()}</span> },
  ];

  return <DataTable columns={columns} data={jobs} keyField="id" loading={loading} error={error} onRetry={fetchJobs} />;
}

function ScheduledTasksTab() {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTasks = useCallback(() => {
    setLoading(true);
    adminApi
      .get<{ items: ScheduledTask[] }>("/admin/logs/scheduled-tasks")
      .then((r) => {
        setTasks(r.items);
        setError(null);
      })
      .catch((err) => {
        setTasks([]);
        setError(toErrorMessage(err, "Failed to load scheduled tasks."));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  const columns = [
    { key: "task_name", label: "Task", render: (v: unknown) => <span className="font-medium text-white">{String(v)}</span> },
    { key: "schedule_cron", label: "Schedule", render: (v: unknown) => <span className="font-mono text-xs text-slate-400">{String(v)}</span> },
    {
      key: "is_active",
      label: "Active",
      render: (v: unknown) => <span className={v ? "text-emerald-400" : "text-slate-500"}>{v ? "Yes" : "No"}</span>,
    },
    {
      key: "last_run_at",
      label: "Last Run",
      render: (v: unknown) => <span className="text-slate-400">{v ? new Date(String(v)).toLocaleString() : "Never"}</span>,
    },
    {
      key: "last_status",
      label: "Last Status",
      render: (v: unknown) => <span className="text-slate-300">{v ? String(v) : "—"}</span>,
    },
  ];

  return (
    <div className="space-y-2">
      <div className="mb-2 flex items-center gap-2 text-sm text-slate-400">
        <Clock className="h-4 w-4" />
        Cron-based background maintenance tasks
      </div>
      <DataTable columns={columns} data={tasks} keyField="id" loading={loading} error={error} onRetry={fetchTasks} />
    </div>
  );
}
