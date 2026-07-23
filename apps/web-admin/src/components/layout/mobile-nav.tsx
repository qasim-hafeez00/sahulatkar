"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";

import { Sidebar } from "@/components/layout/sidebar";
import type { AdminRole } from "@/lib/admin-modules";

type MobileNavProps = {
  role?: AdminRole;
};

/**
 * Hamburger + slide-in drawer for the ~35 admin modules below the `xl`
 * breakpoint, where dashboard/layout.tsx hides the persistent <Sidebar />
 * entirely (`hidden w-72 shrink-0 xl:block`). Without this, there is no way
 * to navigate between modules on tablet/laptop-width screens.
 */
export function MobileNav({ role }: MobileNavProps) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  // Close the drawer whenever the route changes (e.g. after tapping a
  // sidebar link) so it doesn't stay open over the newly-loaded page.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Lock body scroll while the drawer is open so the page behind it
  // doesn't scroll along with the overlay.
  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open navigation menu"
        aria-expanded={open}
        className="flex items-center justify-center rounded-full border border-white/10 bg-white/5 p-2.5 text-slate-300 transition hover:border-white/20 hover:text-white xl:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex xl:hidden">
          <button
            type="button"
            aria-label="Close navigation menu"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
          />
          <div className="relative flex h-full w-full max-w-xs flex-col p-3">
            <div className="mb-2 flex justify-end">
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation menu"
                className="flex items-center justify-center rounded-full border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:border-white/20 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="min-h-0 flex-1">
              <Sidebar role={role} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
