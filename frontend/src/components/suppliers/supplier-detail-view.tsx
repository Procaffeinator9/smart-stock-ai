"use client";

import { ArrowLeft, ArrowUpRight, CalendarCheck, Clock3, PackageX, Wallet } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

import { DataNotice } from "@/components/dashboard/data-notice";
import { KpiCard } from "@/components/dashboard/kpi-cards";
import { cardClassName, fadeUp } from "@/components/ui/card";
import { cn } from "@/lib/cn";
import type { DatasetDates, FreshnessView } from "@/lib/dashboard/live-data";
import { formatCurrencyCompact, formatInteger, formatPercent } from "@/lib/format";
import { supplierLinks } from "@/lib/suppliers/query";
import type { SupplierDetail } from "@/lib/suppliers/types";

import { FlagList } from "./flag-chips";
import { LateDistributionCard } from "./late-distribution-card";
import { MonthlyOnTimeCard } from "./monthly-on-time-card";
import { SuppliedProductsCard } from "./supplied-products-card";
import { SupplierDefinitions } from "./supplier-definitions";
import { formatDays, rateOrDash } from "./supplier-format";
import { SupplierOrdersCard } from "./supplier-orders-card";

const note = (text: string) => <span className="text-xs text-ink-subtle">{text}</span>;

interface SupplierDetailViewProps {
  data: SupplierDetail;
  freshness: FreshnessView;
  dates: DatasetDates;
}

export function SupplierDetailView({ data, freshness, dates }: SupplierDetailViewProps) {
  const { supplier, scorecard: row } = data;
  const links = supplierLinks(supplier.supplier_id, supplier.supplier_name);
  const gap = row.lead_time_gap_days;
  const link = "inline-flex items-center gap-1 rounded-lg border border-line bg-white px-2.5 py-1.5 text-xs font-medium text-ink shadow-sm hover:border-line-strong";

  return (
    <motion.div initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.06 } } }} className="space-y-5">
      <Link href="/suppliers" className="inline-flex items-center gap-1.5 text-[13px] font-medium text-brand hover:text-brand-strong">
        <ArrowLeft aria-hidden className="size-4" /> All suppliers
      </Link>

      <DataNotice meta={{ source: data.source, seed: null }} freshness={freshness} dates={dates} definitionsHref="#supplier-definitions" />

      <motion.section variants={fadeUp} aria-labelledby="supplier-name" className={cn(cardClassName, "space-y-4 p-5")}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 id="supplier-name" className="text-xl font-semibold tracking-tight text-ink">
              {supplier.supplier_name}
            </h2>
            <p className="mt-1 text-[13px] text-ink-muted">
              {supplier.supplier_id} · {supplier.contact_email} (synthetic) · stated lead time {supplier.stated_lead_time_days} days · minimum
              order {formatInteger(supplier.minimum_order_quantity)} units · stated reliability {formatPercent(supplier.stated_reliability)}
            </p>
          </div>
          <nav aria-label="Related pages" className="flex flex-wrap gap-2">
            <Link href={links.orders} className={link}>
              All orders <ArrowUpRight aria-hidden className="size-3.5" />
            </Link>
            {row.overdue_orders > 0 && (
              <Link href={links.overdueOrders} className={link}>
                Overdue orders <ArrowUpRight aria-hidden className="size-3.5" />
              </Link>
            )}
            <Link href={links.sales} className={link}>
              Sales <ArrowUpRight aria-hidden className="size-3.5" />
            </Link>
            <Link href={row.at_risk_positions > 0 ? links.atRiskStock : links.stock} className={link}>
              {row.at_risk_positions > 0 ? "At-risk stock" : "Stock"} <ArrowUpRight aria-hidden className="size-3.5" />
            </Link>
          </nav>
        </div>
        <div>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-subtle">Needs attention</h3>
          <FlagList flags={row.flags} />
        </div>
      </motion.section>

      <motion.div variants={{ show: { transition: { staggerChildren: 0.07 } } }} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Observed on-time rate"
          icon={CalendarCheck}
          accent="bg-emerald-50 text-emerald-700 ring-emerald-600/15"
          value={row.on_time_rate ?? 0}
          format={formatPercent}
          definition=""
          delta={note(`${formatInteger(row.on_time)} of ${formatInteger(row.sample_size)} orders · stated ${formatPercent(row.stated_reliability)}`)}
          footer={
            row.recent_on_time_rate === null
              ? "Overdue open orders count as late."
              : `Last 30 days ${rateOrDash(row.recent_on_time_rate)} (${row.recent_sample} orders) vs ${rateOrDash(row.previous_on_time_rate)} before (${row.previous_sample}).`
          }
        />
        <KpiCard
          label="Observed lead time"
          icon={Clock3}
          accent="bg-sky-50 text-sky-700 ring-sky-600/10"
          value={row.observed_lead_time_days ?? 0}
          format={formatDays}
          definition=""
          delta={note(`stated ${row.stated_lead_time_days} days${gap === null ? "" : ` · ${gap >= 0 ? "+" : "−"}${Math.abs(gap).toFixed(1)} days`}`)}
          footer={
            row.avg_days_late === null
              ? "No order from this supplier was delivered late."
              : `${formatInteger(row.late)} orders delivered late, ${formatDays(row.avg_days_late)} late on average.`
          }
        />
        <KpiCard
          label="Spend"
          icon={Wallet}
          accent="bg-brand-soft text-brand ring-brand/10"
          value={row.spend}
          format={formatCurrencyCompact}
          definition=""
          delta={note(`${formatInteger(row.orders)} orders · ${formatInteger(row.open_orders)} open · ${formatInteger(row.overdue_orders)} overdue`)}
          footer={`${formatInteger(row.cancelled)} cancelled (${rateOrDash(row.cancellation_rate)}), by order date. Spend excludes them.`}
        />
        <KpiCard
          label="At-risk stock positions"
          icon={PackageX}
          accent="bg-red-50 text-red-600 ring-red-600/10"
          value={row.at_risk_positions}
          format={formatInteger}
          definition=""
          delta={note(`of ${formatInteger(row.positions)} positions · ${formatInteger(row.products)} products`)}
          footer={`${formatInteger(row.stockout_days)} stockout days on these products: a correlation, not proof the supplier caused them.`}
        />
      </motion.div>

      <div className="grid gap-5 xl:grid-cols-3">
        <MonthlyOnTimeCard months={data.monthly} statedReliability={supplier.stated_reliability} className="xl:col-span-2" />
        <LateDistributionCard buckets={data.late_distribution} overdue={row.overdue_orders} />
      </div>

      <SuppliedProductsCard products={data.products} revenue={row.revenue} period={data.period} />
      <SupplierOrdersCard overdue={data.overdue_orders} recent={data.recent_orders} totalOrders={row.orders} links={links} />

      <SupplierDefinitions />
    </motion.div>
  );
}
