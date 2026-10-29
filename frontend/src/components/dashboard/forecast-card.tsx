"use client";

import { Activity } from "lucide-react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import type { Forecast } from "@/lib/dashboard/types";
import { formatCompact, formatDateRange, formatInteger, formatShortDate, formatWeekdayDate } from "@/lib/format";

import { AXIS_TICK, ChartFrame, ChartTooltipCard, GRID_STROKE, useChartAnimation } from "./chart-utils";

interface ForecastRow {
  date: string;
  actual?: number;
  projected?: number;
  band?: [number, number];
}

export function ForecastCard({ forecast, className }: { forecast: Forecast; className?: string }) {
  const animate = useChartAnimation();
  const { history, projection } = forecast;

  if (!history.length || !projection.length) {
    return (
      <Card title="Demand forecast preview" className={className}>
        <EmptyState icon={Activity} title="Not enough history for a projection" />
      </Card>
    );
  }

  const lastActual = history.at(-1)!;
  const rows: ForecastRow[] = [
    ...history.map((point) => ({ date: point.date, actual: point.units })),
    ...projection.map((point) => ({ date: point.date, projected: point.units, band: [point.low, point.high] as [number, number] })),
  ];
  // Join the projected line to the last observed day.
  rows[history.length - 1] = { ...rows[history.length - 1], projected: lastActual.units };
  const projectedTotal = projection.reduce((sum, p) => sum + p.units, 0);
  const projectionStart = projection[0].date;
  const projectionEnd = projection.at(-1)!.date;

  return (
    <Card
      title="Demand forecast preview"
      description="Units per day, all stores"
      className={className}
      action={
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700 ring-1 ring-inset ring-slate-500/10">
          Baseline · not ML
        </span>
      }
      footer={`${forecast.method}. The shaded band is the lowest–highest of those four weeks.`}
      bodyClassName="flex flex-col"
    >
      <div className="mb-3">
        <p className="text-2xl font-semibold tracking-tight text-ink">≈ {formatCompact(projectedTotal)} units</p>
        <p className="text-xs text-ink-subtle">projected for {formatDateRange(projectionStart, projectionEnd)}</p>
      </div>
      <ChartFrame
        height={200}
        grow
        summary={`Last ${history.length} days of units sold and a ${projection.length}-day baseline projection totalling about ${formatInteger(projectedTotal)} units.`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
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
            <YAxis tickFormatter={(v: number) => formatCompact(v)} tick={AXIS_TICK} tickLine={false} axisLine={false} width={44} />
            <Tooltip
              cursor={{ stroke: "#c7cdf9", strokeWidth: 1.5 }}
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload as ForecastRow;
                const lines = [];
                if (row.actual !== undefined) lines.push({ label: "Actual", value: formatInteger(row.actual), color: "#0b1630" });
                if (row.band) {
                  lines.push({ label: "Baseline", value: formatInteger(row.projected ?? 0), color: "#4f46e5" });
                  lines.push({ label: "Range", value: `${formatInteger(row.band[0])}–${formatInteger(row.band[1])}` });
                }
                return <ChartTooltipCard title={formatWeekdayDate(String(label))} rows={lines} />;
              }}
            />
            <Area
              dataKey="band"
              stroke="none"
              fill="#4f46e5"
              fillOpacity={0.1}
              isAnimationActive={animate}
              animationDuration={700}
            />
            <Line
              dataKey="actual"
              stroke="#0b1630"
              strokeWidth={1.75}
              dot={false}
              activeDot={{ r: 3.5, strokeWidth: 2, stroke: "#fff" }}
              isAnimationActive={animate}
              animationDuration={700}
            />
            <Line
              dataKey="projected"
              stroke="#4f46e5"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
              activeDot={{ r: 3.5, strokeWidth: 2, stroke: "#fff" }}
              isAnimationActive={animate}
              animationBegin={500}
              animationDuration={700}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartFrame>
    </Card>
  );
}
