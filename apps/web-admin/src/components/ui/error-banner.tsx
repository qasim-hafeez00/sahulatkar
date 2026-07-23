"use client";

import { AlertTriangle, RotateCw } from "lucide-react";

type ErrorBannerProps = {
  message: string;
  onRetry?: () => void;
  className?: string;
};

/**
 * Consistent, visible error state for failed data fetches. Use this instead of
 * silently swallowing fetch errors (e.g. `.catch(() => setData([]))`) so the
 * admin can tell the difference between "no data" and "the request failed."
 */
export function ErrorBanner({ message, onRetry, className = "" }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className={`flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 ${className}`}
    >
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
        <span>{message}</span>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="flex shrink-0 items-center gap-1.5 rounded-full bg-rose-500/20 px-3 py-1.5 text-xs font-semibold text-rose-100 transition hover:bg-rose-500/30"
        >
          <RotateCw className="h-3.5 w-3.5" />
          Retry
        </button>
      )}
    </div>
  );
}

export function toErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}
