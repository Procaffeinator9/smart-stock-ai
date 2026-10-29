"use client";

import { Package, PackageX, TriangleAlert, Wallet, type LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";

import { cardClassName, fadeUp } from "@/components/ui/card";
import { CountUp } from "@/components/ui/count-up";
import { Sparkline } from "@/components/ui/sparkline";
import { cn } from "@/lib/cn";
import { lastDays } from "@/lib/dashboard/selectors";
import type { OverviewData } from "@/lib/dashboard/types";
import { formatCurrencyCompact, formatInteger, formatShortDate } from "@/lib/format";

import { DeltaChip, directionOf, signedNumber, signedPercent } from "./delta-chip";

export interface KpiCardProps {
  label: string;
  icon: LucideIcon;
  accent: string; // icon tile classes
  value: number;
  format: (value: number) => string;
  definition: string;
  delta?: ReactNode;
  trend?: { values: number[]; color: string };
  footer?: ReactNode;
}

export function KpiCard({ label, icon: Icon, accent, value, format, definition, delta, trend, footer }: KpiCardProps) {
  return (
    <motion.article variants={fadeUp} className={cn(cardClassName, "flex flex-col gap-4 p-5")} aria-label={label}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] font-medium text-ink-muted">{label}</p>
        <span className={cn("grid size-8 place-items-center rounded-lg ring-1 ring-inset", accent)}>
          <Icon aria-hidden className="size-4" strokeWidth={2} />
        </span>
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <CountUp value={value} format={format} className="block text-[28px] font-semibold leading-none tracking-tight text-ink" />
          <div className="mt-2.5 min-h-5">{delta}</div>
        </div>
        {trend && <Sparkline values={trend.values} color={trend.color} className="h-9 w-24 shrink-0 sm:w-28" />}
      </div>
      <p className="mt-auto text-xs leading-5 text-ink-subtle">{footer ?? definition}</p>
    </motion.article>
  );
}

export function KpiCards({ data, days }: { data: OverviewData; days: number }) {
  const { kpis, daily, meta } = data;
  const current = kpis.current;
  const since = lastDays(daily.dates, days)[0];
  const context = `since ${formatShortDate(since)}`;

  const valueSeries = lastDays(daily.inventory_value, days);
  const lowSeries = lastDays(daily.low_stock_products, days);
  const riskSeries = lastDays(daily.stockout_risk_products, days);
  const valueChange = (valueSeries.at(-1)! - valueSeries[0]) / valueSeries[0];
  const lowChange = lowSeries.at(-1)! - lowSeries[0];
  const riskChange = riskSeries.at(-1)! - riskSeries[0];

  return (
    <motion.div
      variants={{ show: { transition: { staggerChildren: 0.07 } } }}
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
    >
      <KpiCard
        label="Total products"
        icon={Package}
        accent="bg-brand-soft text-brand ring-brand/10"
        value={kpis.total_products}
        format={formatInteger}
        definition=""
        delta={
          <span className="text-xs text-ink-subtle">
            {kpis.categories} categories · {kpis.suppliers} suppliers
          </span>
        }
        footer={`Stocked across ${kpis.stores} stores (${formatInteger(current.inventory_units)} units on hand).`}
      />
      <KpiCard
        label="Inventory value"
        icon={Wallet}
        accent="bg-sky-50 text-sky-700 ring-sky-600/10"
        value={current.inventory_value}
        format={formatCurrencyCompact}
        definition={`At cost, end of day ${formatShortDate(meta.as_of)}.`}
        delta={<DeltaChip text={signedPercent(valueChange)} direction={directionOf(valueChange)} goodWhen="neutral" context={context} />}
        trend={{ values: valueSeries, color: "#0ea5e9" }}
      />
      <KpiCard
        label="Low-stock products"
        icon={TriangleAlert}
        accent="bg-amber-50 text-amber-700 ring-amber-600/15"
        value={current.low_stock_products}
        format={formatInteger}
        definition="Network-wide available at or below total reorder point."
        delta={<DeltaChip text={signedNumber(lowChange)} direction={directionOf(lowChange)} goodWhen="down" context={context} />}
        trend={{ values: lowSeries, color: "#f59e0b" }}
      />
      <KpiCard
        label="Stockout-risk products"
        icon={PackageX}
        accent="bg-red-50 text-red-600 ring-red-600/10"
        value={current.stockout_risk_products}
        format={formatInteger}
        definition="At least one store below safety stock or out of stock."
        delta={<DeltaChip text={signedNumber(riskChange)} direction={directionOf(riskChange)} goodWhen="down" context={context} />}
        trend={{ values: riskSeries, color: "#ef4444" }}
      />
    </motion.div>
  );
}
