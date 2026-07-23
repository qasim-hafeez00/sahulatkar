import Link from 'next/link';
import { ArrowLeft, Calendar, Phone, ShieldAlert, UserCircle2 } from 'lucide-react';
import { adminApiServer, GatewayRequestError } from '@/lib/admin-api-server';

type UserDetailResponse = {
  requested_by: {
    admin_id: number;
    email: string;
  };
  user: {
    id: number;
    phone: string;
    status: string;
    created_at: string;
    failed_login_attempts: number;
    locked_until: string | null;
  } | null;
  tabs: string[];
};

function formatDate(value: string | null) {
  if (!value) return 'None';
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export default async function UserDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // Only a genuine 404 means "this user doesn't exist" -- any other
  // failure (network error, 5xx, auth) should surface as a real error
  // instead of being silently repainted as a misleading "not found" state.
  const response = await adminApiServer
    .get<UserDetailResponse>(`/admin/users/${id}`)
    .catch((err) => {
      if (err instanceof GatewayRequestError && err.status === 404) return null;
      throw err;
    });

  if (!response?.user) {
    return (
      <section className="space-y-6">
        <Link href="/dashboard/users" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white">
          <ArrowLeft className="h-4 w-4" />
          Back to users
        </Link>
        <div className="glass-panel rounded-2xl p-8 text-center">
          <p className="text-sm uppercase tracking-[0.3em] text-slate-500">AD-03</p>
          <h1 className="mt-3 text-2xl font-semibold text-white">User not found</h1>
          <p className="mt-2 text-sm text-slate-400">The requested user record is unavailable or has been removed.</p>
        </div>
      </section>
    );
  }

  const { user } = response;

  return (
    <section className="space-y-6">
      <Link href="/dashboard/users" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white">
        <ArrowLeft className="h-4 w-4" />
        Back to users
      </Link>

      <div className="glass-panel rounded-3xl p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AD-03 / User 360</p>
            <h1 className="mt-2 text-3xl font-semibold text-white">{user.phone}</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-400">
              Read-only user profile with status, activity and operational risk context.
            </p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
            <div>Requested by {response.requested_by.email}</div>
            <div className="text-slate-500">Admin #{response.requested_by.admin_id}</div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <UserCircle2 className="h-4 w-4 text-blue-400" />
            Status
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{user.status}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Phone className="h-4 w-4 text-emerald-400" />
            Phone
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{user.phone}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Calendar className="h-4 w-4 text-amber-400" />
            Created
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{formatDate(user.created_at)}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <ShieldAlert className="h-4 w-4 text-red-400" />
            Failed logins
          </div>
          <p className="mt-2 text-xl font-semibold text-white">{user.failed_login_attempts}</p>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="glass-panel rounded-3xl p-6 xl:col-span-2">
          <h2 className="text-lg font-semibold text-white">Profile details</h2>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">User ID</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{user.id}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Locked until</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{formatDate(user.locked_until)}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Joined</dt>
              <dd className="mt-2 text-lg font-semibold text-white">{formatDate(user.created_at)}</dd>
            </div>
            <div className="rounded-2xl bg-slate-950/60 p-4">
              <dt className="text-xs uppercase tracking-[0.2em] text-slate-500">Available tabs</dt>
              <dd className="mt-2 text-sm text-slate-300">{response.tabs.join(' · ')}</dd>
            </div>
          </dl>
        </div>

        <div className="glass-panel rounded-3xl p-6">
          <h2 className="text-lg font-semibold text-white">Operational notes</h2>
          <p className="mt-4 text-sm leading-6 text-slate-400">
            This view is intended for support and operations review. Add account actions, financial history and compliance notes as the next iteration.
          </p>
        </div>
      </div>
    </section>
  );
}
