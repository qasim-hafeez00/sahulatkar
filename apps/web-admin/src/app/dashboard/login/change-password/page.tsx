"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function ChangePasswordPage() {
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (newPassword.length < 10) {
      setError("New password must be at least 10 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await fetch("/api/gateway/admin/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(typeof body.detail === "string" ? body.detail : "Could not update your password.");
        return;
      }
      router.push("/dashboard/login?passwordChanged=1");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-6 py-10">
      <div className="glass-panel w-full rounded-[2rem] p-8 sm:p-10">
        <p className="text-xs uppercase tracking-[0.32em] text-amber-200">Required</p>
        <h1 className="mt-3 text-2xl font-semibold text-white">Set a new password</h1>
        <p className="mt-3 text-sm leading-6 text-slate-300">
          Your account requires a password change before you can continue.
        </p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">
              Current password
            </label>
            <input
              type="password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-amber-400/60"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">
              New password (min. 10 characters)
            </label>
            <input
              type="password"
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-amber-400/60"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">
              Confirm new password
            </label>
            <input
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-amber-400/60"
            />
          </div>

          {error && (
            <p className="rounded-xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-full bg-amber-400 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-amber-300 disabled:opacity-60"
          >
            {isSubmitting ? "Updating..." : "Update password"}
          </button>
        </form>
      </div>
    </div>
  );
}
