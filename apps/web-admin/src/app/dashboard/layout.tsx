import type { ReactNode } from "react";
import { cookies } from "next/headers";

import { Sidebar } from "@/components/layout/sidebar";
import { MobileNav } from "@/components/layout/mobile-nav";
import { LogoutButton } from "@/components/layout/logout-button";
import { ADMIN_SESSION_COOKIE, verifyAdminToken } from "@/lib/admin-session";
import type { AdminRole } from "@/lib/admin-modules";

export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const token = cookies().get(ADMIN_SESSION_COOKIE)?.value;
  const session = token ? await verifyAdminToken(token) : null;
  const role = (session?.token_type === "admin" ? session.role : undefined) as AdminRole | undefined;

  return (
    <div className="mx-auto flex min-h-screen max-w-[96rem] gap-6 p-4 sm:p-6 lg:p-8">
      <div className="hidden w-72 shrink-0 xl:block">
        <Sidebar role={role} />
      </div>
      <main className="flex min-w-0 flex-1 flex-col gap-6">
        <header className="glass-panel rounded-[2rem] px-6 py-5">
          <div className="flex items-center gap-3">
            <MobileNav role={role} />
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">M12 Admin Dashboard</p>
          </div>
          <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold text-white">Command center</h1>
              <p className="mt-1 text-sm text-slate-400">Operational visibility for AD-01 to AD-28.</p>
            </div>
            <div className="flex items-center gap-3">
              <div className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-4 py-2 text-xs font-semibold text-emerald-200">
                {role ? role.replace(/_/g, " ") : "Protected admin surface"}
              </div>
              {role && <LogoutButton />}
            </div>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
