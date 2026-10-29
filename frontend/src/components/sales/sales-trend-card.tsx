"use client";

import { LineChart as LineChartIcon } from "lucide-react";
import { useId, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS_TICK, ChartFrame, ChartTooltipCard, GRID_STROKE, useChartAnimation } from "@/components/dashboard/chart-utils";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SegmentedControl } from "@/components/ui/segmented-control";
import {
  formatCompact,
  formatCurrency,
  formatCurrencyCompact,
  formatDateRange,
  formatInteger,
  formatShortDate,
  formatWeekdayDate,
} from "@/lib/format";
import { trendPoints, type Grain, type TrendPoint } from "@/lib/sales/series";
import type { SalesDailySeries, SalesPeriod } from "@/lib/sales/types";

type Metric = "revenue" | "units" | "gross_margin";

const METRICS = [
  { value: "revenue" as const, label: "Revenue" },
  { value: "units" as const, label: "Units" },
  { value: "gross_margin" as const, label: "Margin" },
];

const GRAINS = [
  { value: "daily" as const, label: "Daily" },
  { value: "weekly" as const, label: "Weekly", title: "Weeks start on Monday" },
];

const SERIES: Record<Metric, { label: string; color: string; axis: (v: number) => string; value: (v: number) => string }> = {
  revenue: { label: "Revenue", color: "#4f46e5", axis: formatCurrencyCompact, value: formatCurrency },
  units: { label: "Units sold", color: "#0ea5e9", axis: formatCompact, value: formatInteger },
  gross_margin: { label: "Gross margin", color: "#10b981", axis: formatCurrencyCompact, value: formatCurrency },
};

const PROMO_COLOR = "#8b5cf6";

function pointLabel(point: TrendPoint, grain: Grain): string {
  if (grain === "daily") return formatWeekdayDate(point.start);
  const range = point.start === point.end ? formatShortDate(point.start) : `${formatShortDate(point.start)} – ${formatShortDate(point.end)}`;
  return point.days < 7 ? `${range} (${point.days} days)` : range;
}

export function SalesTrendCard({ daily, period, className }: { daily: SalesDailySeries; period: SalesPeriod; className?: string }) {
  const [metric, setMetric] = useState<Metric>("revenue");
  const [grain, setGrain] = useState<Grain>(period.days > 45 ? "weekly" : "daily");
  const gradientId = useId().replace(/:/g, "");
  const animate = useChartAnimation();
  const points = trendPoints(daily, grain);
  const series = SERIES[metric];
  const total = points.reduce((sum, p) => sum + p[metric], 0);
  const hasSales = daily.units.some((units) => units > 0);
  const showPromo = metric === "revenue" && daily.promo_revenue.some((value) => value > 0);
  const summary = `${series.label} per ${grain === "daily" ? "day" : "week"} from ${formatDateRange(period.date_from, period.date_to)}, total ${series.value(total)}.`;

  return (
    <Card
      title="Sales trend"
      description={formatDateRange(period.date_from, period.date_to)}
      className={className}
      bodyClassName="flex flex-col"
      action={
        <div className="flex flex-wrap gap-2">
          <SegmentedControl label="Sales metric" options={METRICS} value={metric} onChange={setMetric} />
          <SegmentedControl label="Group by" options={GRAINS} value={grain} onChange={setGrain} />
        </div>
      }
    >
      {!hasSales ? (
        <EmptyState icon={LineChartIcon} title="No sales match these filters" description="Try a longer date range or fewer filters." />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <p className="text-2xl font-semibold tracking-tight text-ink tabular-nums">{series.value(total)}</p>
            {showPromo && (
              <p className="flex items-center gap-1.5 text-xs text-ink-subtle">
                <span className="size-2 rounded-full" style={{ background: PROMO_COLOR }} /> of which on promotion
              </p>
            )}
          </div>
          <ChartFrame height={260} grow summary={summary}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={points} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={series.color} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={series.color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 4" vertical={false} />
                <XAxis
                  dataKey="start"
                  tickFormatter={(value: string) => formatShortDate(value)}
                  tick={AXIS_TICK}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={28}
                  tickMargin={8}
                />
                <YAxis tickFormatter={(value: number) => series.axis(value)} tick={AXIS_TICK} tickLine={false} axisLine={false} width={56} />
                <Tooltip
                  cursor={{ stroke: "#c7cdf9", strokeWidth: 1.5 }}
                  content={({ active, payload }) => {
                    const point = payload?.[0]?.payload as TrendPoint | undefined;
                    if (!active || !point) return null;
                    const rows = [{ label: series.label, value: series.value(point[metric]), color: series.color }];
                    if (showPromo) rows.push({ label: "On promotion", value: formatCurrency(point.promo_revenue), color: PROMO_COLOR });
                    return <ChartTooltipCard title={pointLabel(point, grain)} rows={rows} />;
                  }}
                />
                <Area
                  type="monotone"
                  dataKey={metric}
                  stroke={series.color}
                  strokeWidth={2}
                  fill={`url(#${gradientId})`}
                  activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff", fill: series.color }}
                  isAnimationActive={animate}
                  animationDuration={700}
                />
                {showPromo && (
                  <Area
                    type="monotone"
                    dataKey="promo_revenue"
                    stroke={PROMO_COLOR}
                    strokeWidth={1.5}
                    strokeDasharray="4 3"
                    fill={PROMO_COLOR}
                    fillOpacity={0.08}
                    activeDot={{ r: 3, strokeWidth: 2, stroke: "#fff", fill: PROMO_COLOR }}
                    isAnimationActive={animate}
                    animationDuration={700}
                  />
                )}
              </AreaChart>
            </ResponsiveContainer>
          </ChartFrame>
        </>
      )}
    </Card>
  );
}
