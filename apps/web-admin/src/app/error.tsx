"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCw } from "lucide-react";

export default function GlobalRouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("Unhandled error in web-admin route:", error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-10">
      <div className="glass-panel w-full max-w-lg rounded-[2rem] p-8 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-rose-500/30 bg-rose-500/10">
          <AlertTriangle className="h-7 w-7 text-rose-400" />
        </div>
        <p className="mt-5 text-xs uppercase tracking-[0.3em] text-slate-500">Something went wrong</p>
        <h1 className="mt-3 text-2xl font-semibold text-white">This page hit an unexpected error</h1>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          The request failed and the admin console couldn&apos;t render this page. You can retry, or head
          back to the command center if the problem persists.
        </p>
        {error.message && (
          <p className="mt-4 rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3 text-left font-mono text-xs text-slate-400">
            {error.message}
          </p>
        )}
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="flex items-center gap-2 rounded-full bg-amber-400 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-amber-300"
          >
            <RotateCw className="h-4 w-4" />
            Try again
          </button>
          <a
            href="/dashboard"
            className="rounded-full border border-white/15 bg-white/5 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10"
          >
            Back to command center
          </a>
        </div>
      </div>
    </div>
  );
}
