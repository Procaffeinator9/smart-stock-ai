import { Skeleton } from "@/components/ui/skeleton";

const card = "rounded-2xl border border-line bg-surface p-5 shadow-card";

/** Placeholder for the Suppliers pages while their data loads. */
export function SupplierSkeleton({ label = "Loading suppliers…" }: { label?: string }) {
  return (
    <div className="space-y-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">{label}</span>
      <Skeleton className="h-11 w-full rounded-xl" />
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
        <Skeleton className="h-4 w-40" />
        <div className="mt-5 space-y-3">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="flex items-center gap-4">
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-3.5 w-48 max-w-full" />
                <Skeleton className="h-3 w-32" />
              </div>
              <Skeleton className="hidden h-5 w-28 rounded-full sm:block" />
              <Skeleton className="h-4 w-14" />
              <Skeleton className="hidden h-4 w-16 md:block" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
