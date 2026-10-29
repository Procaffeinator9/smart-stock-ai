"use client";

import { motion } from "motion/react";

import { useShell } from "@/components/shell/shell-context";
import { rangeDays } from "@/lib/dashboard/date-range";
import type { DatasetDates, FreshnessView } from "@/lib/dashboard/live-data";
import type { OverviewData } from "@/lib/dashboard/types";

import { CategoryBreakdownCard } from "./category-breakdown-card";
import { DataNotice } from "./data-notice";
import { ForecastCard } from "./forecast-card";
import { InventoryAlertsCard } from "./inventory-alerts-card";
import { KpiCards } from "./kpi-cards";
import { PurchaseOrdersCard } from "./purchase-orders-card";
import { SalesTrendCard } from "./sales-trend-card";
import { StoreHealthCard } from "./store-health-card";

/** Composes the overview widgets; each block fades up in sequence on first render. */
interface OverviewDashboardProps {
  data: OverviewData;
  freshness: FreshnessView;
  dates: DatasetDates;
}

export function OverviewDashboard({ data, freshness, dates }: OverviewDashboardProps) {
  const { range } = useShell();
  const days = rangeDays(range);

  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.06 } } }}
      className="space-y-5"
    >
      <DataNotice meta={data.meta} freshness={freshness} dates={dates} />
      <KpiCards data={data} days={days} />

      <div className="grid gap-5 xl:grid-cols-3">
        <SalesTrendCard daily={data.daily} days={days} className="xl:col-span-2" />
        <CategoryBreakdownCard daily={data.daily} days={days} categories={data.meta.categories} />
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <InventoryAlertsCard
          alerts={data.alerts}
          positions={data.kpis.current.positions}
          asOf={data.meta.as_of}
          className="xl:col-span-2"
        />
        <StoreHealthCard stores={data.store_health} positions={data.kpis.current.positions} />
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <ForecastCard forecast={data.forecast} />
        <PurchaseOrdersCard
          summary={data.purchase_orders.summary}
          recent={data.purchase_orders.recent}
          overdue={data.purchase_orders.overdue}
          className="xl:col-span-2"
        />
      </div>
    </motion.div>
  );
}
