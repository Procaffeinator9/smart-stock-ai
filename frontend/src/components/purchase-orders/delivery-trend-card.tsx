"use client";

import { BarChart3 } from "lucide-react";
import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS_TICK, ChartFrame, ChartTooltipCard, GRID_STROKE, useChartAnimation } from "@/components/dashboard/chart-utils";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { formatCompact, formatCurrency, formatCurrencyCompact, formatInteger, formatPercent, formatShortDate } from "@/lib/format";
import type { PurchaseOrderSummary, WeeklyDelivery, WeeklyOrders } from "@/lib/purchase-orders/types";

type View = "delivery" | "orders";

const VIEWS = [
  { value: "delivery" as const, label: "Delivery", title: "Outcomes by week of the promised date" },
  { value: "orders" as const, label: "Orders placed", title: "Orders placed per week, by order date" },
];

const COLORS = { on_time: "#10b981", late: "#f59e0b", overdue: "#ef4444", rate: "#4f46e5", value: "#4f46e5" };

function weekLabel(week: { date_from: string; date_to: string; days: number }): string {
  const range = `${formatShortDate(week.date_from)} – ${formatShortDate(week.date_to)}`;
  return week.days < 7 ? `${range} (${week.days} days)` : range;
}

export function DeliveryTrendCard({ summary, className }: { summary: PurchaseOrderSummary; className?: string }) {
  const [view, setView] = useState<View>("delivery");
  const animate = useChartAnimation();
  const delivery = summary.weekly_delivery;
  const placed = summary.weekly_orders;
  const empty = view === "delivery" ? delivery.length === 0 : placed.every((w) => w.orders === 0);

  const summaryText =
    view === "delivery"
      ? `Weekly delivery outcomes by promised date: ${delivery
          .map((w) => `${weekLabel(w)} ${w.on_time} on time, ${w.late} late, ${w.overdue} overdue`)
          .join("; ")}.`
      : `Orders placed per week: ${placed.map((w) => `${weekLabel(w)} ${w.orders} orders, ${formatCurrency(w.value)}`).join("; ")}.`;

  return (
    <Card
      title={view === "delivery" ? "Delivery performance" : "Orders placed"}
      description={
        view === "delivery"
          ? "Orders by week of their promised date: on time, late, or still overdue, with the weekly on-time rate"
          : "Order value per week (weeks start on Monday), by order date"
      }
      className={className}
      bodyClassName="flex flex-col"
      action={<SegmentedControl label="Chart" options={VIEWS} value={view} onChange={setView} />}
    >
      {empty ? (
        <EmptyState icon={BarChart3} title="No orders for these filters" description="Try a wider date range or fewer filters." />
      ) : (
        <>
          {view === "delivery" && (
            <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-subtle">
              {(
                [
                  ["On time", COLORS.on_time],
                  ["Delivered late", COLORS.late],
                  ["Overdue (open)", COLORS.overdue],
                ] as const
              ).map(([label, color]) => (
                <li key={label} className="flex items-center gap-1.5">
                  <span className="size-2 rounded-sm" style={{ background: color }} /> {label}
                </li>
              ))}
              <li className="flex items-center gap-1.5">
                <span className="h-0.5 w-3 rounded" style={{ background: COLORS.rate }} /> On-time rate
              </li>
            </ul>
          )}
          <ChartFrame height={260} grow summary={summaryText}>
            <ResponsiveContainer width="100%" height="100%">
              {view === "delivery" ? (
                <ComposedChart data={delivery} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 4" vertical={false} />
                  <XAxis dataKey="date_from" tickFormatter={(v: string) => formatShortDate(v)} tick={AXIS_TICK} tickLine={false} axisLine={false} minTickGap={20} tickMargin={8} />
                  <YAxis yAxisId="orders" tickFormatter={(v: number) => formatCompact(v)} tick={AXIS_TICK} tickLine={false} axisLine={false} width={40} />
                  <YAxis
                    yAxisId="rate"
                    orientation="right"
                    domain={[0, 1]}
                    tickFormatter={(v: number) => formatPercent(v)}
                    tick={AXIS_TICK}
                    tickLine={false}
                    axisLine={false}
                    width={44}
                  />
                  <Tooltip
                    cursor={{ fill: "#eef0fb", opacity: 0.6 }}
                    content={({ active, payload }) => {
                      const week = payload?.[0]?.payload as WeeklyDelivery | undefined;
                      if (!active || !week) return null;
                      return (
                        <ChartTooltipCard
                          title={`Promised ${weekLabel(week)}`}
                          rows={[
                            { label: "On time", value: formatInteger(week.on_time), color: COLORS.on_time },
                            { label: "Delivered late", value: formatInteger(week.late), color: COLORS.late },
                            { label: "Overdue", value: formatInteger(week.overdue), color: COLORS.overdue },
                            { label: "On-time rate", value: week.on_time_rate === null ? "—" : formatPercent(week.on_time_rate), color: COLORS.rate },
                          ]}
                        />
                      );
                    }}
                  />
                  <Bar yAxisId="orders" dataKey="on_time" stackId="outcome" fill={COLORS.on_time} isAnimationActive={animate} />
                  <Bar yAxisId="orders" dataKey="late" stackId="outcome" fill={COLORS.late} isAnimationActive={animate} />
                  <Bar yAxisId="orders" dataKey="overdue" stackId="outcome" fill={COLORS.overdue} radius={[3, 3, 0, 0]} isAnimationActive={animate} />
                  <Line
                    yAxisId="rate"
                    type="monotone"
                    dataKey="on_time_rate"
                    stroke={COLORS.rate}
                    strokeWidth={2}
                    dot={{ r: 2.5, fill: COLORS.rate, strokeWidth: 0 }}
                    connectNulls
                    isAnimationActive={animate}
                  />
                </ComposedChart>
              ) : (
                <ComposedChart data={placed} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 4" vertical={false} />
                  <XAxis dataKey="date_from" tickFormatter={(v: string) => formatShortDate(v)} tick={AXIS_TICK} tickLine={false} axisLine={false} minTickGap={20} tickMargin={8} />
                  <YAxis tickFormatter={(v: number) => formatCurrencyCompact(v)} tick={AXIS_TICK} tickLine={false} axisLine={false} width={56} />
                  <Tooltip
                    cursor={{ fill: "#eef0fb", opacity: 0.6 }}
                    content={({ active, payload }) => {
                      const week = payload?.[0]?.payload as WeeklyOrders | undefined;
                      if (!active || !week) return null;
                      return (
                        <ChartTooltipCard
                          title={`Ordered ${weekLabel(week)}`}
                          rows={[
                            { label: "Value", value: formatCurrency(week.value), color: COLORS.value },
                            { label: "Orders", value: formatInteger(week.orders) },
                            { label: "Units", value: formatInteger(week.units) },
                            { label: "Cancelled", value: formatInteger(week.cancelled) },
                          ]}
                        />
                      );
                    }}
                  />
                  <Bar dataKey="value" fill={COLORS.value} radius={[3, 3, 0, 0]} isAnimationActive={animate} />
                </ComposedChart>
              )}
            </ResponsiveContainer>
          </ChartFrame>
        </>
      )}
    </Card>
  );
}
