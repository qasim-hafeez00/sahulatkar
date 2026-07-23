import Link from "next/link";

export default function ForbiddenPage() {
  return (
    <div className="mx-auto flex min-h-screen max-w-2xl items-center px-6 py-10">
      <div className="glass-panel w-full rounded-[2rem] p-8 sm:p-10">
        <p className="text-xs uppercase tracking-[0.32em] text-amber-200">Access denied</p>
        <h1 className="mt-3 text-3xl font-semibold text-white">Your role can&apos;t access this module.</h1>
        <p className="mt-4 text-sm leading-7 text-slate-300">
          If you believe this is a mistake, contact a Super Admin to review your role assignment.
        </p>
        <Link
          href="/dashboard"
          className="mt-8 inline-flex rounded-full bg-amber-400 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-amber-300"
        >
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}
