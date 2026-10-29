"use client";

import { Truck } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS_TICK, ChartFrame, ChartTooltipCard, GRID_STROKE, useChartAnimation } from "@/components/dashboard/chart-utils";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { formatCurrency, formatCurrencyCompact, formatDateRange, formatInteger, formatShortDate, formatWeekdayDate } from "@/lib/format";
import type { PurchaseOrderSummary } from "@/lib/purchase-orders/types";

interface InboundScheduleCardProps {
  inbound: PurchaseOrderSummary["inbound"];
  overdue: number;
  className?: string;
}

/** Open orders by promised date over the 14 days starting on the as-of date. */
export function InboundScheduleCard({ inbound, overdue, className }: InboundScheduleCardProps) {
  const animate = useChartAnimation();
  const days = inbound.days.map((d, i) => ({ ...d, label: i === 0 ? "As of" : formatShortDate(d.date) }));
  const summary = `Open orders due per day from ${formatDateRange(inbound.date_from, inbound.date_to)}: ${inbound.days
    .map((d) => `${formatShortDate(d.date)} ${d.orders}`)
    .join(", ")}.`;

  return (
    <Card
      title="Inbound, next 14 days"
      description={`Open orders by promised date, ${formatDateRange(inbound.date_from, inbound.date_to)}`}
      className={className}
      bodyClassName="flex flex-col"
      footer={
        <>
          Also {formatInteger(overdue)} overdue (promised earlier) and {formatInteger(inbound.later.orders)} promised later. Day one is the
          dataset&apos;s as-of date.
        </>
      }
    >
      {inbound.orders === 0 ? (
        <EmptyState icon={Truck} title="Nothing due in the next 14 days" />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-baseline gap-x-3">
            <p className="text-2xl font-semibold tracking-tight text-ink tabular-nums">{formatInteger(inbound.orders)}</p>
            <p className="text-xs text-ink-subtle">
              orders · {formatInteger(inbound.units)} units · {formatCurrencyCompact(inbound.value)}
            </p>
          </div>
          <ChartFrame height={200} grow summary={summary}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={days} margin={{ top: 6, right: 4, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 4" vertical={false} />
                <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} minTickGap={12} tickMargin={8} />
                <YAxis allowDecimals={false} tick={AXIS_TICK} tickLine={false} axisLine={false} width={32} />
                <Tooltip
                  cursor={{ fill: "#eef0fb", opacity: 0.6 }}
                  content={({ active, payload }) => {
                    const day = payload?.[0]?.payload as (typeof days)[number] | undefined;
                    if (!active || !day) return null;
                    return (
                      <ChartTooltipCard
                        title={`${formatWeekdayDate(day.date)}${day.date === inbound.date_from ? " (as of)" : ""}`}
                        rows={[
                          { label: "Orders due", value: formatInteger(day.orders), color: "#0ea5e9" },
                          { label: "Units", value: formatInteger(day.units) },
                          { label: "Value", value: formatCurrency(day.value) },
                        ]}
                      />
                    );
                  }}
                />
                <Bar dataKey="orders" radius={[3, 3, 0, 0]} isAnimationActive={animate}>
                  {days.map((d, i) => (
                    <Cell key={d.date} fill={i === 0 ? "#6366f1" : "#0ea5e9"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartFrame>
        </>
      )}
    </Card>
  );
}
