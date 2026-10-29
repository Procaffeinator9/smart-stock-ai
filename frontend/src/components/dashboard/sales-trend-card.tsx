"use client";

import { LineChart as LineChartIcon } from "lucide-react";
import { useId, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card } from "@/components/ui/card";
import { CountUp } from "@/components/ui/count-up";
import { EmptyState } from "@/components/ui/empty-state";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { comparePeriods, salesPoints } from "@/lib/dashboard/selectors";
import type { DailySeries } from "@/lib/dashboard/types";
import {
  formatCompact,
  formatCurrency,
  formatCurrencyCompact,
  formatDateRange,
  formatInteger,
  formatShortDate,
  formatWeekdayDate,
} from "@/lib/format";

import { AXIS_TICK, ChartFrame, ChartTooltipCard, GRID_STROKE, useChartAnimation } from "./chart-utils";
import { DeltaChip, directionOf, signedPercent } from "./delta-chip";

type Metric = "revenue" | "units";

const METRICS = [
  { value: "revenue" as const, label: "Revenue" },
  { value: "units" as const, label: "Units" },
];

const FORMAT: Record<Metric, { total: (v: number) => string; axis: (v: number) => string; tooltip: (v: number) => string }> = {
  revenue: { total: formatCurrency, axis: formatCurrencyCompact, tooltip: formatCurrency },
  units: { total: formatInteger, axis: formatCompact, tooltip: formatInteger },
};

export function SalesTrendCard({ daily, days, className }: { daily: DailySeries; days: number; className?: string }) {
  const [metric, setMetric] = useState<Metric>("revenue");
  const gradientId = useId().replace(/:/g, "");
  const animate = useChartAnimation();
  const points = salesPoints(daily, days);
  const comparison = comparePeriods(daily[metric], days);
  const format = FORMAT[metric];

  const first = points[0]?.date;
  const last = points.at(-1)?.date;
  const summary = first
    ? `${metric === "revenue" ? "Revenue" : "Units sold"} per day from ${formatDateRange(first, last!)}, total ${format.total(comparison.current)}.`
    : "No sales in this range.";

  return (
    <Card
      title="Sales trend"
      description={first ? formatDateRange(first, last!) : undefined}
      className={className}
      bodyClassName="flex flex-col"
      action={<SegmentedControl label="Sales metric" options={METRICS} value={metric} onChange={setMetric} />}
    >
      {points.length === 0 ? (
        <EmptyState icon={LineChartIcon} title="No sales in this range" description="Choose a longer date range." />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-end gap-x-4 gap-y-2">
            <CountUp
              key={metric}
              value={comparison.current}
              format={format.total}
              className="text-2xl font-semibold tracking-tight text-ink"
            />
            {comparison.change !== null ? (
              <DeltaChip
                text={signedPercent(comparison.change)}
                direction={directionOf(comparison.change)}
                goodWhen="up"
                context={`vs previous ${days} days`}
              />
            ) : (
              <span className="text-xs text-ink-subtle">No earlier period in the dataset to compare</span>
            )}
          </div>
          <ChartFrame height={260} grow summary={summary}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={points} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#4f46e5" stopOpacity={0.22} />
                    <stop offset="100%" stopColor="#4f46e5" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 4" vertical={false} />
                <XAxis
                  dataKey="date"
                  tickFormatter={(value: string) => formatShortDate(value)}
                  tick={AXIS_TICK}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={28}
                  tickMargin={8}
                />
                <YAxis
                  tickFormatter={(value: number) => format.axis(value)}
                  tick={AXIS_TICK}
                  tickLine={false}
                  axisLine={false}
                  width={56}
                />
                <Tooltip
                  cursor={{ stroke: "#c7cdf9", strokeWidth: 1.5 }}
                  content={({ active, payload, label }) =>
                    active && payload?.length ? (
                      <ChartTooltipCard
                        title={formatWeekdayDate(String(label))}
                        rows={[
                          {
                            label: metric === "revenue" ? "Revenue" : "Units sold",
                            value: format.tooltip(Number(payload[0].value)),
                            color: "#4f46e5",
                          },
                        ]}
                      />
                    ) : null
                  }
                />
                <Area
                  type="monotone"
                  dataKey={metric}
                  stroke="#4f46e5"
                  strokeWidth={2}
                  fill={`url(#${gradientId})`}
                  activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff", fill: "#4f46e5" }}
                  isAnimationActive={animate}
                  animationDuration={700}
                />
              </AreaChart>
            </ResponsiveContainer>
          </ChartFrame>
        </>
      )}
    </Card>
  );
}
