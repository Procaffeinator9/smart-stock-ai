import { Skeleton } from "@/components/ui/skeleton";

const card = "rounded-2xl border border-line bg-surface p-5 shadow-card";

/** Placeholder for the Overview while its data loads (route transitions and the Suspense fallback). */
export function OverviewSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading dashboard…</span>
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
      <div className="grid gap-5 xl:grid-cols-3">
        <div className={`${card} xl:col-span-2`}>
          <Skeleton className="h-4 w-32" />
          <Skeleton className="mt-6 h-[260px] w-full" />
        </div>
        <div className={card}>
          <Skeleton className="h-4 w-40" />
          <Skeleton className="mx-auto mt-6 size-44 rounded-full" />
        </div>
      </div>
    </div>
  );
}
