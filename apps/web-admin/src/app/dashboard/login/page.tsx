import Link from "next/link";

export default function AdminLoginPage() {
  return (
    <div className="mx-auto flex min-h-screen max-w-2xl items-center px-6 py-10">
      <div className="glass-panel w-full rounded-[2rem] p-8 sm:p-10">
        <p className="text-xs uppercase tracking-[0.32em] text-amber-200">Admin access</p>
        <h1 className="mt-3 text-3xl font-semibold text-white">Sign-in flow will land here next.</h1>
        <p className="mt-4 text-sm leading-7 text-slate-300">
          The route is already reserved for dashboard protection middleware and will be connected to the
          admin JWT login flow once the auth handoff is wired.
        </p>
        <Link
          href="/"
          className="mt-8 inline-flex rounded-full bg-amber-400 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-amber-300"
        >
          Back to landing
        </Link>
      </div>
    </div>
  );
}
