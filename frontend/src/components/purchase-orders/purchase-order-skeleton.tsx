import { Skeleton } from "@/components/ui/skeleton";

const card = "rounded-2xl border border-line bg-surface p-5 shadow-card";

/** Placeholder for the Purchase Orders page while its data loads. */
export function PurchaseOrderSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading purchase orders…</span>
      <Skeleton className="h-11 w-full rounded-xl" />
      <div className={`${card} space-y-3`}>
        <div className="flex flex-wrap gap-3">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-72 self-center" />
        </div>
        <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-[11rem_14rem_11rem_18rem]">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-9" />
          ))}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {[96, 90, 104, 100, 104].map((width, i) => (
            <Skeleton key={i} className="h-8 rounded-full" style={{ width }} />
          ))}
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className={card}>
            <Skeleton className="h-4 w-28" />
            <Skeleton className="mt-5 h-8 w-24" />
            <Skeleton className="mt-4 h-3 w-40" />
          </div>
        ))}
      </div>
      <div className={card}>
        <Skeleton className="h-4 w-36" />
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      </div>
    </div>
  );
}
