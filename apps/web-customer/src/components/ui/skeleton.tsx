import * as React from "react"
import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "shimmer rounded-lg bg-[var(--section-bg)]",
        className
      )}
      {...props}
    />
  )
}

/** Mirrors the ready-state product card layout so the pending → ready swap doesn't jump. */
function SkeletonProductCard() {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex-1 space-y-3">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-3.5 w-1/2" />
        <div className="flex items-center justify-between pt-1">
          <Skeleton className="h-6 w-28" />
          <Skeleton className="h-4 w-24" />
        </div>
      </div>
      <Skeleton className="h-5 w-5 shrink-0 rounded-md" />
    </div>
  )
}

export { Skeleton, SkeletonProductCard }
