"use client";

import { Database, PackageSearch } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { usePathname, useRouter } from "next/navigation";
import { useOptimistic, useRef, useState, useTransition } from "react";

import { useShell } from "@/components/shell/shell-context";
import { cardClassName } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/cn";
import { DEFAULT_QUERY, hasActiveFilters, toSearchParams, type InventoryQuery, type SortField } from "@/lib/inventory/query";
import type { InventoryPage } from "@/lib/inventory/types";
import { formatLongDate } from "@/lib/format";

import { InventoryFilters } from "./inventory-filters";
import { InventoryPagination } from "./inventory-pagination";
import { InventoryTable } from "./inventory-table";

const SOURCE_LABEL = { csv: "Synthetic CSV files (local)", databricks: "Databricks (unverified)" } as const;

export function InventoryWorklist({ data, query }: { data: InventoryPage; query: InventoryQuery }) {
  const router = useRouter();
  const pathname = usePathname();
  const { openAbout } = useShell();
  const reduceMotion = useReducedMotion();
  const [isPending, startTransition] = useTransition();
  // Controls reflect the new choice immediately; the table updates when the server responds.
  const [current, setCurrent] = useOptimistic(query);
  const [searchKey, setSearchKey] = useState(0);
  const topRef = useRef<HTMLDivElement>(null);

  function navigate(next: InventoryQuery) {
    const qs = toSearchParams(next).toString();
    startTransition(() => {
      setCurrent(next);
      router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  }

  const update = (patch: Partial<InventoryQuery>) => navigate({ ...current, ...patch, page: 1 });
  const onSort = (sort: SortField) =>
    update({ sort, order: current.sort === sort && current.order === "asc" ? "desc" : "asc" });
  const onPage = (page: number) => {
    navigate({ ...current, page });
    topRef.current?.scrollIntoView({ block: "start", behavior: reduceMotion ? "auto" : "smooth" });
  };
  const clear = () => {
    setSearchKey((key) => key + 1); // reset the uncontrolled search input
    navigate({ ...DEFAULT_QUERY, sort: current.sort, order: current.order, pageSize: current.pageSize });
  };
  const active = hasActiveFilters(current);

  return (
    <motion.div
      ref={topRef}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="scroll-mt-24 space-y-3"
    >
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
        <Database aria-hidden className="size-3.5 text-ink-subtle" />
        <span>
          Read-only · Source: <span className="font-medium text-ink">{SOURCE_LABEL[data.source]}</span> · Snapshot{" "}
          {formatLongDate(data.as_of)}
        </span>
        <button type="button" onClick={openAbout} className="font-medium text-brand hover:text-brand-strong">
          How statuses are calculated
        </button>
      </p>

      <section aria-label="Inventory worklist" className={cn(cardClassName, "overflow-hidden")}>
        <div className="p-4 sm:p-5">
          <InventoryFilters
            query={current}
            facets={data.facets}
            summary={data.summary}
            onChange={update}
            onClear={clear}
            searchKey={searchKey}
            active={active}
          />
        </div>

        <div aria-busy={isPending} className="relative">
          {isPending && (
            <div role="progressbar" aria-label="Loading results" className="absolute inset-x-0 top-0 z-10 h-0.5 overflow-hidden bg-brand-soft">
              <div className="h-full w-1/3 animate-[indeterminate_1.1s_ease-in-out_infinite] bg-brand" />
            </div>
          )}
          <div className={cn("transition-opacity duration-200", isPending && "pointer-events-none opacity-55")}>
            {data.total === 0 ? (
              <EmptyState
                icon={PackageSearch}
                title="No positions match these filters"
                description="Try a different search term, store, category, or status."
                action={
                  active && (
                    <button
                      type="button"
                      onClick={clear}
                      className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-medium text-ink shadow-sm hover:border-line-strong"
                    >
                      Clear filters
                    </button>
                  )
                }
                className="border-t border-line py-14"
              />
            ) : data.items.length === 0 ? (
              <EmptyState
                icon={PackageSearch}
                title={`Page ${data.page} is past the end`}
                description={`There are ${data.total_pages} pages for these filters.`}
                action={
                  <button
                    type="button"
                    onClick={() => onPage(data.total_pages)}
                    className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-medium text-ink shadow-sm hover:border-line-strong"
                  >
                    Go to last page
                  </button>
                }
                className="border-t border-line py-14"
              />
            ) : (
              <InventoryTable rows={data.items} asOf={data.as_of} sort={current.sort} order={current.order} onSort={onSort} />
            )}
          </div>
        </div>

        {data.total > 0 && (
          <div className="border-t border-line px-4 py-3 sm:px-5">
            <InventoryPagination
              page={current.page}
              pageSize={current.pageSize}
              total={data.total}
              totalPages={data.total_pages}
              onPage={onPage}
              onPageSize={(pageSize) => update({ pageSize })}
            />
          </div>
        )}
      </section>
    </motion.div>
  );
}
