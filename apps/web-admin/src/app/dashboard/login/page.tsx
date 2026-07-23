"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

type LoginResult =
  | { status: "ok"; role: string; admin_id: number }
  | { status: "force_password_change" }
  | { status: "mfa_setup_required" }
  | { status: "totp_required" }
  | { status: "error"; message: string };

export default function AdminLoginPage() {
  return (
    <Suspense fallback={null}>
      <AdminLoginForm />
    </Suspense>
  );
}

function AdminLoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const notice =
    searchParams.get("mfa") === "enabled"
      ? "Two-factor authentication enabled. Please sign in again."
      : searchParams.get("passwordChanged") === "1"
        ? "Password updated. Please sign in again."
        : null;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [needsTotp, setNeedsTotp] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password,
          totp_code: needsTotp && totpCode ? totpCode : undefined,
        }),
      });
      const result: LoginResult = await response.json();

      switch (result.status) {
        case "ok":
          router.push("/dashboard");
          router.refresh();
          return;
        case "force_password_change":
          router.push("/dashboard/login/change-password");
          return;
        case "mfa_setup_required":
          router.push("/dashboard/login/mfa-setup");
          return;
        case "totp_required":
          setNeedsTotp(true);
          setError("Enter the 6-digit code from your authenticator app.");
          return;
        case "error":
        default:
          setError(result.message ?? "Login failed.");
      }
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-6 py-10">
      <div className="glass-panel w-full rounded-[2rem] p-8 sm:p-10">
        <p className="text-xs uppercase tracking-[0.32em] text-amber-200">Admin access</p>
        <h1 className="mt-3 text-2xl font-semibold text-white">Sign in to SahulatKar Admin</h1>

        {notice && (
          <p className="mt-4 rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-200">
            {notice}
          </p>
        )}

        <form onSubmit={handleSubmit} className="mt-8 space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">
              Email
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-amber-400/60"
              placeholder="admin@sahulatkar.pk"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-amber-400/60"
              placeholder="••••••••"
            />
          </div>

          {needsTotp && (
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">
                Authenticator code
              </label>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                required
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-center font-mono text-lg tracking-[0.5em] text-white outline-none focus:border-amber-400/60"
                placeholder="000000"
              />
            </div>
          )}

          {error && (
            <p className="rounded-xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="mt-2 w-full rounded-full bg-amber-400 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-amber-300 disabled:opacity-60"
          >
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
