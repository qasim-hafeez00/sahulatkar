"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCw } from "lucide-react";

// Scoped to src/app/dashboard/**: this is where nearly all of the admin
// console's data-fetching (adminApi / adminApiServer calls against the
// gateway) happens, so a failed request here is caught by this boundary
// instead of bubbling up to the root error.tsx -- the sidebar and header
// from dashboard/layout.tsx stay mounted and usable while only the
// content area shows the error.
export default function DashboardSectionError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("Unhandled error in an admin dashboard module:", error);
  }, [error]);

  return (
    <section className="glass-panel rounded-[2rem] p-8 text-center">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-rose-500/30 bg-rose-500/10">
        <AlertTriangle className="h-7 w-7 text-rose-400" />
      </div>
      <p className="mt-5 text-xs uppercase tracking-[0.3em] text-slate-500">Module failed to load</p>
      <h1 className="mt-3 text-2xl font-semibold text-white">This admin module hit an error</h1>
      <p className="mt-2 text-sm leading-6 text-slate-400">
        The data for this section couldn&apos;t be loaded. This is usually a temporary gateway or
        network issue -- try again.
      </p>
      {error.message && (
        <p className="mx-auto mt-4 max-w-xl rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3 text-left font-mono text-xs text-slate-400">
          {error.message}
        </p>
      )}
      <div className="mt-6 flex items-center justify-center">
        <button
          type="button"
          onClick={reset}
          className="flex items-center gap-2 rounded-full bg-amber-400 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-amber-300"
        >
          <RotateCw className="h-4 w-4" />
          Try again
        </button>
      </div>
    </section>
  );
}
