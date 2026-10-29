"use client";

import { BadgePercent, CircleDollarSign, Coins, Package } from "lucide-react";
import { motion } from "motion/react";

import { DeltaChip, directionOf, signedPercent } from "@/components/dashboard/delta-chip";
import { KpiCard } from "@/components/dashboard/kpi-cards";
import { formatCurrencyCompact, formatCurrencyPrecise, formatInteger, formatPercent } from "@/lib/format";
import type { SalesSummary } from "@/lib/sales/types";

import { roundedChange } from "./change-text";

function relativeChange(current: number, previous: number | undefined): number | null {
  return previous === undefined || previous === 0 ? null : (current - previous) / previous;
}

/** Change between two ratios in percentage points. */
function signedPoints(current: number | null, previous: number | null | undefined): number | null {
  return current === null || previous === null || previous === undefined ? null : (current - previous) * 100;
}

/** "+1.2 pts" / "−0.4 pts" / "0.0 pts". */
function pointsText(points: number): string {
  const rounded = Math.round(points * 10) / 10;
  return `${rounded > 0 ? "+" : rounded < 0 ? "−" : ""}${Math.abs(rounded).toFixed(1)} pts`;
}

export function SalesKpiCards({ summary }: { summary: SalesSummary }) {
  const { current, previous } = summary.kpis;
  // Exact dates are in the filter bar's caption; the chip stays short next to the sparkline.
  const context = summary.previous_period ? `vs previous ${formatInteger(summary.previous_period.days)} days` : undefined;
  const noComparison = <span className="text-xs text-ink-subtle">No earlier period in the data to compare</span>;

  function delta(change: number | null) {
    if (change === null) return noComparison;
    const rounded = roundedChange(change);
    return <DeltaChip text={signedPercent(rounded)} direction={directionOf(rounded)} goodWhen="up" context={context} />;
  }

  const shareChange = signedPoints(current.promo_revenue_share, previous?.promo_revenue_share);
  const marginRate = current.margin_rate === null ? "—" : formatPercent(current.margin_rate);
  const previousRate = previous?.margin_rate;

  return (
    <motion.div variants={{ show: { transition: { staggerChildren: 0.07 } } }} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard
        label="Revenue"
        icon={CircleDollarSign}
        accent="bg-brand-soft text-brand ring-brand/10"
        value={current.revenue}
        format={formatCurrencyCompact}
        definition=""
        delta={delta(relativeChange(current.revenue, previous?.revenue))}
        trend={{ values: summary.daily.revenue, color: "#4f46e5" }}
        footer={
          current.avg_unit_price === null
            ? "No sales in this period."
            : `Average ${formatCurrencyPrecise(current.avg_unit_price)} per unit across ${formatInteger(current.sale_lines)} daily store-product sales.`
        }
      />
      <KpiCard
        label="Units sold"
        icon={Package}
        accent="bg-sky-50 text-sky-700 ring-sky-600/10"
        value={current.units}
        format={formatInteger}
        definition=""
        delta={delta(relativeChange(current.units, previous?.units))}
        trend={{ values: summary.daily.units, color: "#0ea5e9" }}
        footer={`${formatInteger(current.products_sold)} products sold · ${formatInteger(current.stockout_days)} store-days out of stock.`}
      />
      <KpiCard
        label="Gross margin"
        icon={Coins}
        accent="bg-emerald-50 text-emerald-700 ring-emerald-600/15"
        value={current.gross_margin}
        format={formatCurrencyCompact}
        definition=""
        delta={delta(relativeChange(current.gross_margin, previous?.gross_margin))}
        trend={{ values: summary.daily.gross_margin, color: "#10b981" }}
        footer={`${marginRate} of revenue${previousRate != null ? ` (was ${formatPercent(previousRate)})` : ""}, at standard unit cost.`}
      />
      <KpiCard
        label="Promotional share"
        icon={BadgePercent}
        accent="bg-violet-50 text-violet-700 ring-violet-600/15"
        value={current.promo_revenue_share ?? 0}
        format={formatPercent}
        definition=""
        delta={
          shareChange === null ? (
            noComparison
          ) : (
            <DeltaChip
              text={pointsText(shareChange)}
              direction={directionOf(Math.round(shareChange * 10) / 10)}
              goodWhen="neutral"
              context={context}
            />
          )
        }
        footer={`${formatCurrencyCompact(current.promo_revenue)} of revenue and ${formatInteger(current.promo_units)} units sold on promotion.`}
      />
    </motion.div>
  );
}
