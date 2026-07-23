"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

export default function MfaSetupPage() {
  const router = useRouter();
  const [secret, setSecret] = useState("");
  const [qrUri, setQrUri] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const requestedRef = useRef(false);

  useEffect(() => {
    // /mfa/setup issues a brand-new secret on every call (not idempotent), so
    // React 18 StrictMode's dev-mode double-invoke would silently overwrite
    // the secret shown to the user with a second one — guard against that.
    if (requestedRef.current) return;
    requestedRef.current = true;

    fetch("/api/gateway/admin/auth/mfa/setup", { method: "POST" })
      .then(async (res) => {
        if (!res.ok) {
          setError("Could not start MFA setup. Please sign in again.");
          return;
        }
        const data = await res.json();
        setSecret(data.secret);
        setQrUri(data.qr_uri);
      })
      .finally(() => setLoaded(true));
  }, []);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const res = await fetch("/api/gateway/admin/auth/mfa/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ totp_code: totpCode }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(typeof body.detail === "string" ? body.detail : "Invalid code. Please try again.");
        return;
      }
      router.push("/dashboard/login?mfa=enabled");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-6 py-10">
      <div className="glass-panel w-full rounded-[2rem] p-8 sm:p-10">
        <p className="text-xs uppercase tracking-[0.32em] text-amber-200">Required</p>
        <h1 className="mt-3 text-2xl font-semibold text-white">Set up two-factor authentication</h1>
        <p className="mt-3 text-sm leading-6 text-slate-300">
          MFA is mandatory for every admin account. Add this key to Google Authenticator, Authy, or a similar app.
        </p>

        {!loaded ? (
          <p className="mt-6 text-sm text-slate-400">Loading...</p>
        ) : error && !secret ? (
          <p className="mt-6 rounded-xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">
            {error}
          </p>
        ) : (
          <>
            <div className="mt-6 rounded-xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs uppercase tracking-wide text-slate-400">Manual entry key</p>
              <p className="mt-1 break-all font-mono text-sm text-amber-200">{secret}</p>
              <p className="mt-3 text-xs uppercase tracking-wide text-slate-400">Provisioning URI</p>
              <p className="mt-1 break-all font-mono text-xs text-slate-400">{qrUri}</p>
            </div>

            <form onSubmit={handleVerify} className="mt-6 space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">
                  Enter the 6-digit code
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

              {error && (
                <p className="rounded-xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={isSubmitting || totpCode.length !== 6}
                className="w-full rounded-full bg-amber-400 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-amber-300 disabled:opacity-60"
              >
                {isSubmitting ? "Verifying..." : "Enable MFA"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
