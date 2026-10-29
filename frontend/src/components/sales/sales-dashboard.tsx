"use client";

import { motion, useReducedMotion } from "motion/react";
import { usePathname, useRouter } from "next/navigation";
import { useOptimistic, useRef, useState, useTransition } from "react";

import { CategoryShareCard } from "@/components/dashboard/category-breakdown-card";
import { DataNotice } from "@/components/dashboard/data-notice";
import { cn } from "@/lib/cn";
import type { DatasetDates, FreshnessView } from "@/lib/dashboard/live-data";
import { DEFAULT_SALES_QUERY, hasActiveFilters, nextSort, toSearchParams, type ProductSortField, type SalesQuery } from "@/lib/sales/query";
import type { ProductPerformancePage, SalesSummary } from "@/lib/sales/types";

import { ChangeText } from "./change-text";
import { ProductPerformanceTable } from "./product-performance-table";
import { PromotionCard } from "./promotion-card";
import { SalesDefinitions } from "./sales-definitions";
import { SalesFilters } from "./sales-filters";
import { SalesKpiCards } from "./sales-kpi-cards";
import { SalesTrendCard } from "./sales-trend-card";
import { StoreComparisonCard } from "./store-comparison-card";

interface SalesDashboardProps {
  summary: SalesSummary;
  products: ProductPerformancePage;
  query: SalesQuery;
  freshness: FreshnessView;
  dates: DatasetDates;
}

export function SalesDashboard({ summary, products, query, freshness, dates }: SalesDashboardProps) {
  const router = useRouter();
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();
  const [isPending, startTransition] = useTransition();
  // Controls reflect the new choice immediately; figures update when the server responds.
  const [current, setCurrent] = useOptimistic(query);
  const [searchKey, setSearchKey] = useState(0);
  const tableRef = useRef<HTMLDivElement>(null);

  function navigate(next: SalesQuery) {
    const qs = toSearchParams(next).toString();
    startTransition(() => {
      setCurrent(next);
      router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  }

  const update = (patch: Partial<SalesQuery>) => navigate({ ...current, ...patch, page: 1 });
  const onSort = (field: ProductSortField) => update(nextSort(current, field));
  const onPage = (page: number) => {
    navigate({ ...current, page });
    tableRef.current?.scrollIntoView({ block: "start", behavior: reduceMotion ? "auto" : "smooth" });
  };
  const clear = () => {
    setSearchKey((key) => key + 1); // reset the uncontrolled search input
    navigate({ ...DEFAULT_SALES_QUERY, days: current.days, from: current.from, to: current.to, pageSize: current.pageSize });
  };

  const changes = new Map(summary.by_category.map((c) => [c.category, c.change]));

  return (
    <motion.div initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.06 } } }} className="space-y-5">
      <DataNotice meta={{ source: summary.source, seed: null }} freshness={freshness} dates={dates} definitionsHref="#sales-definitions" />

      <SalesFilters
        query={current}
        summary={summary}
        onChange={update}
        onClear={clear}
        active={hasActiveFilters(current)}
      />

      <div aria-busy={isPending} className="relative">
        {isPending && (
          <div role="progressbar" aria-label="Loading results" className="absolute inset-x-0 -top-3 z-10 h-0.5 overflow-hidden rounded-full bg-brand-soft">
            <div className="h-full w-1/3 animate-[indeterminate_1.1s_ease-in-out_infinite] bg-brand" />
          </div>
        )}
        <div className={cn("space-y-5 transition-opacity duration-200", isPending && "pointer-events-none opacity-55")}>
          <SalesKpiCards summary={summary} />

          <div className="grid gap-5 xl:grid-cols-3">
            <SalesTrendCard daily={summary.daily} period={summary.period} className="xl:col-span-2" />
            <CategoryShareCard
              totals={summary.by_category.map((c) => ({ category: c.category, revenue: c.revenue, share: c.share }))}
              categories={summary.facets.categories}
              description="Share of revenue in this period"
              detail={(category) => <ChangeText change={changes.get(category) ?? null} className="ml-2 text-xs" />}
            />
          </div>

          <div className="grid gap-5 xl:grid-cols-3">
            <StoreComparisonCard stores={summary.by_store} hasPrevious={summary.previous_period !== null} className="xl:col-span-2" />
            <PromotionCard promotion={summary.promotion} filter={summary.filters.promotion} />
          </div>

          <div ref={tableRef} className="scroll-mt-24">
            <ProductPerformanceTable
              page={products}
              query={current}
              searchKey={searchKey}
              onSearch={(search) => update({ search })}
              onSort={onSort}
              onPage={onPage}
              onPageSize={(pageSize) => update({ pageSize })}
              onClear={clear}
            />
          </div>
        </div>
      </div>

      <SalesDefinitions />
    </motion.div>
  );
}
