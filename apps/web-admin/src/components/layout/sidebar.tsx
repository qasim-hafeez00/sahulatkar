"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AdminRole, getVisibleModules } from "@/lib/admin-modules";

type SidebarProps = {
  role?: AdminRole;
};

export function Sidebar({ role }: SidebarProps) {
  const pathname = usePathname();
  const modules = role ? getVisibleModules(role) : [];
  const groups = Array.from(new Set(modules.map((module) => module.group)));

  return (
    <aside className="glass-panel flex h-full flex-col rounded-[2rem] p-4 text-sm text-slate-300">
      <div className="rounded-[1.5rem] border border-white/10 bg-white/5 p-4">
        <p className="text-xs uppercase tracking-[0.32em] text-amber-200">SahulatKar</p>
        <p className="mt-2 text-lg font-semibold text-white">Admin console</p>
        <p className="mt-1 text-xs leading-5 text-slate-400">
          RBAC-aware modules for operations, risk, finance, compliance, analytics, and platform ops.
        </p>
      </div>

      <nav className="mt-4 flex-1 space-y-5 overflow-y-auto pr-1">
        {groups.map((group) => (
          <div key={group} className="space-y-2">
            <p className="px-2 text-[0.68rem] uppercase tracking-[0.3em] text-slate-500">{group}</p>
            <div className="space-y-1">
              {modules
                .filter((module) => module.group === group)
                .map((module) => {
                  const isActive = pathname === module.href || pathname.startsWith(`${module.href}/`);
                  return (
                    <Link
                      key={module.id}
                      href={module.href}
                      className={`flex items-center justify-between rounded-2xl px-3 py-2 transition ${
                        isActive
                          ? "bg-amber-400 text-slate-950"
                          : "border border-transparent bg-white/0 text-slate-300 hover:border-white/10 hover:bg-white/5"
                      }`}
                    >
                      <span>{module.label}</span>
                      <span className={`text-[0.65rem] font-semibold ${isActive ? "text-slate-900" : "text-slate-500"}`}>
                        {module.id}
                      </span>
                    </Link>
                  );
                })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
