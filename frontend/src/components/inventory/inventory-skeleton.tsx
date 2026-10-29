import { cardClassName } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function InventorySkeleton() {
  return (
    <div className="space-y-3" aria-busy="true">
      <span className="sr-only">Loading inventory…</span>
      <Skeleton className="h-4 w-80 max-w-full" />
      <div className={cardClassName}>
        <div className="space-y-3 p-4 sm:p-5">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_11rem_11rem]">
            <Skeleton className="h-9 sm:col-span-2 lg:col-span-1" />
            <Skeleton className="h-9" />
            <Skeleton className="h-9" />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[64, 110, 120, 96, 90].map((width) => (
              <Skeleton key={width} className="h-8 rounded-full" style={{ width }} />
            ))}
          </div>
        </div>
        <div className="divide-y divide-line border-t border-line">
          {Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="flex items-center gap-4 px-5 py-3.5">
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-3.5 w-48 max-w-full" />
                <Skeleton className="h-3 w-32" />
              </div>
              <Skeleton className="hidden h-5 w-20 rounded-full sm:block" />
              <Skeleton className="h-4 w-12" />
              <Skeleton className="hidden h-4 w-16 md:block" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
