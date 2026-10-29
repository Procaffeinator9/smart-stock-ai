"use client";

import { AlarmClock, CalendarCheck, PackageOpen, Timer } from "lucide-react";
import { motion } from "motion/react";

import { KpiCard } from "@/components/dashboard/kpi-cards";
import { formatCurrencyCompact, formatInteger, formatLongDate, formatPercent } from "@/lib/format";
import type { PurchaseOrderSummary } from "@/lib/purchase-orders/types";

const formatDays = (value: number) => `${value.toFixed(1)} days`;
const plural = (n: number, word: string) => `${formatInteger(n)} ${word}${n === 1 ? "" : "s"}`;

export function PurchaseOrderKpiCards({ summary }: { summary: PurchaseOrderSummary }) {
  const { open, overdue, delivery } = summary;
  const rateSeries = summary.weekly_delivery.map((w) => w.on_time_rate).filter((r): r is number => r !== null);
  const note = (text: string) => <span className="text-xs text-ink-subtle">{text}</span>;

  return (
    <motion.div variants={{ show: { transition: { staggerChildren: 0.07 } } }} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard
        label="Open order value"
        icon={PackageOpen}
        accent="bg-brand-soft text-brand ring-brand/10"
        value={open.value}
        format={formatCurrencyCompact}
        definition=""
        delta={note(`${plural(open.orders, "order")} · ${formatInteger(open.units)} units`)}
        trend={{ values: summary.weekly_orders.map((w) => w.value), color: "#4f46e5" }}
        footer="Orders placed or in transit, at unit cost. The line shows the value ordered each week."
      />
      <KpiCard
        label="Overdue orders"
        icon={AlarmClock}
        accent="bg-red-50 text-red-600 ring-red-600/10"
        value={overdue.orders}
        format={formatInteger}
        definition=""
        delta={note(
          overdue.orders === 0
            ? "None past their promised date"
            : `${formatCurrencyCompact(overdue.value)} · average ${formatDays(overdue.avg_days_overdue ?? 0)} overdue (max ${plural(overdue.max_days_overdue ?? 0, "day")})`,
        )}
        footer={`Open and past the promised date as of ${formatLongDate(summary.as_of)}.`}
      />
      <KpiCard
        label="On-time rate"
        icon={CalendarCheck}
        accent="bg-emerald-50 text-emerald-700 ring-emerald-600/15"
        value={delivery.on_time_rate ?? 0}
        format={formatPercent}
        definition=""
        delta={note(
          delivery.on_time_rate === null
            ? "No deliveries or overdue orders yet"
            : `${formatInteger(delivery.on_time)} of ${formatInteger(delivery.delivered + delivery.overdue_open)} orders on time`,
        )}
        trend={rateSeries.length > 1 ? { values: rateSeries, color: "#10b981" } : undefined}
        footer={`Overdue open orders count as late. Delivered orders only: ${
          delivery.delivered_only_on_time_rate === null ? "—" : formatPercent(delivery.delivered_only_on_time_rate)
        } (the Overview's definition).`}
      />
      <KpiCard
        label="Average days late"
        icon={Timer}
        accent="bg-amber-50 text-amber-700 ring-amber-600/15"
        value={delivery.avg_days_late ?? 0}
        format={formatDays}
        definition=""
        delta={note(
          delivery.late === 0
            ? "No order was delivered late"
            : `${plural(delivery.late, "order")} delivered late (max ${plural(delivery.max_days_late ?? 0, "day")})`,
        )}
        footer={
          delivery.avg_actual_lead_days === null
            ? "No deliveries in this scope."
            : `Lead time: promised ${formatDays(delivery.avg_promised_lead_days ?? 0)}, actual ${formatDays(delivery.avg_actual_lead_days)}.`
        }
      />
    </motion.div>
  );
}
