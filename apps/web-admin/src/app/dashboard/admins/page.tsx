"use client";

import { Plus, ShieldCheck, UserCog, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable } from "@/components/admin/data-table";
import { ErrorBanner, toErrorMessage } from "@/components/ui/error-banner";
import { adminApi } from "@/lib/api-client";

interface AdminUserRow {
  id: number;
  email: string;
  role_id: number | null;
  role_name: string | null;
  mfa_enabled: boolean;
  force_password_change: boolean;
  locked_until: string | null;
}

interface RoleEntry {
  name: string;
  permissions: string[];
}

interface SessionEntry {
  id: number;
  admin_id: number;
  admin_email: string;
  ip: string | null;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  is_active: boolean;
}

const TABS = [
  { key: "admins", label: "Admin Users" },
  { key: "roles", label: "Role Hierarchy" },
  { key: "sessions", label: "Active Sessions" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function AdminsPage() {
  const [tab, setTab] = useState<TabKey>("admins");

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-25</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Team &amp; access</h2>
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

      {tab === "admins" && <AdminUsersTab />}
      {tab === "roles" && <RoleHierarchyTab />}
      {tab === "sessions" && <SessionsTab />}
    </section>
  );
}

function AdminUsersTab() {
  const [admins, setAdmins] = useState<AdminUserRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [roles, setRoles] = useState<string[]>([]);
  const [form, setForm] = useState({ email: "", password: "", role: "analyst" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [listError, setListError] = useState<string | null>(null);
  const [rolesError, setRolesError] = useState<string | null>(null);

  const fetchAdmins = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.get<{ items: AdminUserRow[]; pagination: { total: number } }>("/admin/admins?limit=100");
      setAdmins(r.items);
      setTotal(r.pagination.total);
      setListError(null);
    } catch (err) {
      setAdmins([]);
      setListError(toErrorMessage(err, "Failed to load admin users."));
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchRoles = useCallback(async () => {
    try {
      const r = await adminApi.get<{ roles: RoleEntry[] }>("/admin/auth/roles");
      setRoles(r.roles.map((x) => x.name));
      setRolesError(null);
    } catch (err) {
      setRolesError(toErrorMessage(err, "Failed to load role list."));
    }
  }, []);

  useEffect(() => {
    fetchAdmins();
    fetchRoles();
  }, [fetchAdmins, fetchRoles]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await adminApi.post("/admin/auth/admins", form);
      setForm({ email: "", password: "", role: "analyst" });
      setShowForm(false);
      await fetchAdmins();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create admin");
    } finally {
      setSubmitting(false);
    }
  };

  const handleAssignRole = async (adminId: number, currentRole: string | null) => {
    const newRole = prompt(`New role for admin #${adminId} (current: ${currentRole ?? "none"}):\n${roles.join(", ")}`);
    if (!newRole || !roles.includes(newRole)) return;
    await adminApi.put(`/admin/auth/admins/${adminId}/role`, { role: newRole });
    await fetchAdmins();
  };

  const columns = [
    { key: "email", label: "Email", render: (v: unknown) => <span className="font-medium text-white">{String(v)}</span> },
    {
      key: "role_name",
      label: "Role",
      render: (v: unknown) => (
        <span className="rounded-full bg-blue-500/20 px-3 py-1 text-xs font-semibold text-blue-400">
          {v ? String(v).replace(/_/g, " ") : "unassigned"}
        </span>
      ),
    },
    {
      key: "mfa_enabled",
      label: "MFA",
      render: (v: unknown) => (
        <span className={v ? "text-emerald-400" : "text-rose-400"}>{v ? "Enabled" : "Not set up"}</span>
      ),
    },
    {
      key: "locked_until",
      label: "Status",
      render: (v: unknown) => (
        <span className={v ? "text-rose-400" : "text-emerald-400"}>{v ? "Locked" : "Active"}</span>
      ),
    },
    {
      key: "id",
      label: "",
      render: (id: unknown, row: AdminUserRow) => (
        <button
          type="button"
          onClick={() => handleAssignRole(Number(id), row.role_name)}
          className="rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold text-white hover:bg-white/20"
        >
          Change role
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setShowForm((s) => !s)}
          className="flex items-center gap-2 rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          <Plus className="h-4 w-4" />
          Add Admin
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="glass-panel space-y-4 rounded-[2rem] p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Email</label>
              <input
                required
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Temporary password</label>
              <input
                required
                type="password"
                minLength={8}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">Role</label>
              <select
                aria-label="Admin role"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none"
              >
                {roles.map((r) => (
                  <option key={r} value={r}>
                    {r.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {rolesError && <ErrorBanner message={rolesError} onRetry={fetchRoles} />}
          {error && <p className="text-sm text-rose-400">{error}</p>}
          <div className="flex items-center gap-3">
            <button type="submit" disabled={submitting} className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60">
              {submitting ? "Creating..." : "Create admin"}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className="rounded-full px-5 py-2.5 text-sm font-semibold text-slate-400 hover:text-white">
              Cancel
            </button>
          </div>
        </form>
      )}

      <DataTable columns={columns} data={admins} keyField="id" loading={loading} error={listError} onRetry={fetchAdmins} />
      <p className="text-sm text-slate-400">
        Showing <span className="font-semibold text-white">{admins.length}</span> of{" "}
        <span className="font-semibold text-white">{total}</span> admins
      </p>
    </div>
  );
}

function RoleHierarchyTab() {
  const [roles, setRoles] = useState<RoleEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRoleHierarchy = useCallback(() => {
    setLoading(true);
    adminApi
      .get<{ roles: RoleEntry[] }>("/admin/admins/role-hierarchy")
      .then((r) => {
        setRoles(r.roles);
        setError(null);
      })
      .catch((err) => {
        setRoles([]);
        setError(toErrorMessage(err, "Failed to load role hierarchy."));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchRoleHierarchy();
  }, [fetchRoleHierarchy]);

  if (loading) return <div className="h-40 animate-pulse rounded-2xl bg-slate-900/50" />;

  if (error) return <ErrorBanner message={error} onRetry={fetchRoleHierarchy} />;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {roles.map((r) => (
        <div key={r.name} className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-blue-400" />
            <h3 className="font-semibold text-white">{r.name.replace(/_/g, " ")}</h3>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {r.permissions.map((p) => (
              <span key={p} className="rounded-full bg-white/5 px-2.5 py-1 text-xs text-slate-300">
                {p.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function SessionsTab() {
  const [sessions, setSessions] = useState<SessionEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.get<{ items: SessionEntry[] }>("/admin/auth/sessions?active_only=false");
      setSessions(r.items);
      setError(null);
    } catch (err) {
      setSessions([]);
      setError(toErrorMessage(err, "Failed to load active sessions."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleRevoke = async (id: number) => {
    if (!confirm("Revoke this session? The admin will be logged out immediately.")) return;
    await adminApi.post(`/admin/auth/sessions/${id}/revoke`, {});
    await fetchSessions();
  };

  const columns = [
    { key: "admin_email", label: "Admin", render: (v: unknown) => <span className="font-medium text-white">{String(v)}</span> },
    { key: "ip", label: "IP", render: (v: unknown) => <span className="text-slate-400">{v ? String(v) : "—"}</span> },
    {
      key: "created_at",
      label: "Created",
      render: (v: unknown) => <span className="text-slate-400">{new Date(String(v)).toLocaleString()}</span>,
    },
    {
      key: "is_active",
      label: "Status",
      render: (v: unknown) => (
        <span className={v ? "text-emerald-400" : "text-slate-500"}>{v ? "Active" : "Revoked"}</span>
      ),
    },
    {
      key: "id",
      label: "",
      render: (id: unknown, row: SessionEntry) =>
        row.is_active ? (
          <button
            type="button"
            onClick={() => handleRevoke(Number(id))}
            className="rounded-full bg-rose-500/20 px-3 py-1.5 text-xs font-semibold text-rose-400 hover:bg-rose-500/30"
          >
            Revoke
          </button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Users className="h-4 w-4 text-blue-500" />
            Active Sessions
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{sessions.filter((s) => s.is_active).length}</p>
        </div>
        <div className="glass-panel rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <UserCog className="h-4 w-4 text-slate-500" />
            Total (incl. revoked)
          </div>
          <p className="mt-2 text-2xl font-bold text-white">{sessions.length}</p>
        </div>
      </div>
      <DataTable columns={columns} data={sessions} keyField="id" loading={loading} error={error} onRetry={fetchSessions} />
    </div>
  );
}
