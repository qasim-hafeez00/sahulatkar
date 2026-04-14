import Link from "next/link";

import { adminModules } from "@/lib/admin-modules";

type DashboardCatchAllProps = {
  params: {
    slug?: string[];
  };
};

export default function DashboardCatchAllPage({ params }: DashboardCatchAllProps) {
  const path = `/${(params.slug ?? []).join("/")}`;
  const dashboardModule = adminModules.find((item) => item.href === path);

  return (
    <section className="glass-panel rounded-[2rem] p-6">
      <p className="text-xs uppercase tracking-[0.3em] text-slate-400">{dashboardModule?.id ?? "Dashboard module"}</p>
      <h2 className="mt-2 text-2xl font-semibold text-white">{dashboardModule?.label ?? "Module in progress"}</h2>
      <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-400">
        {dashboardModule
          ? `This route is wired into the admin shell and will receive its full implementation in the next slice.`
          : `This placeholder keeps the dashboard navigation functional while the remaining admin modules are implemented.`}
      </p>
      <div className="mt-6 rounded-3xl border border-white/10 bg-white/5 p-5 text-sm text-slate-300">
        Target route: <span className="font-semibold text-white">{path}</span>
      </div>
      <Link href="/dashboard" className="mt-6 inline-flex rounded-full bg-amber-400 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-amber-300">
        Back to dashboard home
      </Link>
    </section>
  );
}
