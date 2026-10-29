"use client";

import { motion, useReducedMotion } from "motion/react";
import { usePathname, useRouter } from "next/navigation";
import { useOptimistic, useRef, useState, useTransition } from "react";

import { DataNotice } from "@/components/dashboard/data-notice";
import { cn } from "@/lib/cn";
import type { DatasetDates, FreshnessView } from "@/lib/dashboard/live-data";
import {
  DEFAULT_PO_QUERY,
  hasActiveFilters,
  nextSort,
  overdueView,
  toSearchParams,
  type OrderSortField,
  type PurchaseOrderQuery,
} from "@/lib/purchase-orders/query";
import type { PurchaseOrderPage, PurchaseOrderSummary } from "@/lib/purchase-orders/types";

import { DeliveryTrendCard } from "./delivery-trend-card";
import { InboundScheduleCard } from "./inbound-schedule-card";
import { OverdueOrdersCard } from "./overdue-orders-card";
import { PurchaseOrderDefinitions } from "./purchase-order-definitions";
import { PurchaseOrderFilters } from "./purchase-order-filters";
import { PurchaseOrderKpiCards } from "./purchase-order-kpi-cards";
import { PurchaseOrderTable } from "./purchase-order-table";

interface PurchaseOrderDashboardProps {
  summary: PurchaseOrderSummary;
  orders: PurchaseOrderPage;
  query: PurchaseOrderQuery;
  freshness: FreshnessView;
  dates: DatasetDates;
}

export function PurchaseOrderDashboard({ summary, orders, query, freshness, dates }: PurchaseOrderDashboardProps) {
  const router = useRouter();
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();
  const [isPending, startTransition] = useTransition();
  // Controls reflect the new choice immediately; figures update when the server responds.
  const [current, setCurrent] = useOptimistic(query);
  const [searchKey, setSearchKey] = useState(0);
  const tableRef = useRef<HTMLDivElement>(null);

  function navigate(next: PurchaseOrderQuery) {
    const qs = toSearchParams(next).toString();
    startTransition(() => {
      setCurrent(next);
      router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  }

  const scrollToTable = () => tableRef.current?.scrollIntoView({ block: "start", behavior: reduceMotion ? "auto" : "smooth" });
  const update = (patch: Partial<PurchaseOrderQuery>) => navigate({ ...current, ...patch, page: 1 });
  const onSort = (field: OrderSortField) => update(nextSort(current, field));
  const onPage = (page: number) => {
    navigate({ ...current, page });
    scrollToTable();
  };
  const clear = () => {
    setSearchKey((key) => key + 1); // reset the uncontrolled search input
    navigate({ ...DEFAULT_PO_QUERY, days: current.days, from: current.from, to: current.to, pageSize: current.pageSize });
  };
  const showOverdue = () => {
    setSearchKey((key) => key + 1);
    navigate(overdueView(current));
    scrollToTable();
  };

  return (
    <motion.div initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.06 } } }} className="space-y-5">
      <DataNotice
        meta={{ source: summary.source, seed: null }}
        freshness={freshness}
        dates={dates}
        definitionsHref="#purchase-order-definitions"
      />

      <PurchaseOrderFilters query={current} summary={summary} onChange={update} onClear={clear} active={hasActiveFilters(current)} />

      <div aria-busy={isPending} className="relative">
        {isPending && (
          <div role="progressbar" aria-label="Loading results" className="absolute inset-x-0 -top-3 z-10 h-0.5 overflow-hidden rounded-full bg-brand-soft">
            <div className="h-full w-1/3 animate-[indeterminate_1.1s_ease-in-out_infinite] bg-brand" />
          </div>
        )}
        <div className={cn("space-y-5 transition-opacity duration-200", isPending && "pointer-events-none opacity-55")}>
          <PurchaseOrderKpiCards summary={summary} />
          <OverdueOrdersCard overdue={summary.overdue} asOf={summary.as_of} onShowAll={showOverdue} />

          <div className="grid gap-5 xl:grid-cols-3">
            <DeliveryTrendCard summary={summary} className="xl:col-span-2" />
            <InboundScheduleCard inbound={summary.inbound} overdue={summary.overdue.orders} />
          </div>

          <div ref={tableRef} className="scroll-mt-24">
            <PurchaseOrderTable
              page={orders}
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

      <PurchaseOrderDefinitions />
    </motion.div>
  );
}
