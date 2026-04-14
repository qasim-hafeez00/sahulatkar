import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen px-6 py-10 text-slate-100 sm:px-10 lg:px-16">
      <div className="mx-auto flex min-h-[80vh] max-w-6xl flex-col justify-center gap-8">
        <div className="inline-flex w-fit items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.28em] text-amber-200">
          SahulatKar BNPL Admin
        </div>
        <div className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
          <section className="glass-panel rounded-[2rem] p-8 sm:p-10">
            <p className="text-sm font-medium uppercase tracking-[0.3em] text-amber-200/90">
              Executive control plane
            </p>
            <h1 className="mt-4 max-w-2xl text-4xl font-semibold leading-tight text-white sm:text-5xl">
              Operate credit, payments, compliance, and support from one admin surface.
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300 sm:text-lg">
              This workspace starts the M12 admin dashboard foundation with protected routing,
              role-aware navigation, and the first data-driven command center for operations.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                className="rounded-full bg-amber-400 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-amber-300"
                href="/dashboard"
              >
                Open dashboard
              </Link>
              <Link
                className="rounded-full border border-white/15 bg-white/5 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/10"
                href="/dashboard/login"
              >
                Admin sign-in
              </Link>
            </div>
          </section>
          <aside className="grid gap-4">
            <div className="glass-panel rounded-3xl p-5">
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Scope</p>
              <p className="mt-3 text-lg font-semibold text-white">AD-01 through AD-28</p>
              <p className="mt-2 text-sm text-slate-300">
                Dashboard, users, orders, payments, risk, finance, compliance, analytics, and platform ops.
              </p>
            </div>
            <div className="glass-panel rounded-3xl p-5">
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Delivery mode</p>
              <p className="mt-3 text-lg font-semibold text-white">Parallel backend and frontend</p>
              <p className="mt-2 text-sm text-slate-300">
                Gateway admin APIs and ledger finance endpoints are being wired alongside the UI.
              </p>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
