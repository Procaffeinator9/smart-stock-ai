"use client";

import { BarChart3 } from "lucide-react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS_TICK, ChartFrame, ChartTooltipCard, GRID_STROKE, useChartAnimation } from "@/components/dashboard/chart-utils";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { formatCompact, formatInteger, formatPercent } from "@/lib/format";
import type { SupplierDetail } from "@/lib/suppliers/types";

const COLORS = { on_time: "#10b981", late: "#f59e0b", overdue: "#ef4444", rate: "#4f46e5", stated: "#94a3b8" };
const monthFormat = new Intl.DateTimeFormat("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
const formatMonth = (iso: string) => monthFormat.format(new Date(`${iso}T00:00:00Z`));

interface MonthlyOnTimeCardProps {
  months: SupplierDetail["monthly"];
  statedReliability: number;
  className?: string;
}

/** Outcomes by month of the promised date, the monthly observed on-time rate, and the stated reliability. */
export function MonthlyOnTimeCard({ months, statedReliability, className }: MonthlyOnTimeCardProps) {
  const animate = useChartAnimation();
  const summary = `Monthly on-time rate by promised date: ${months
    .map((m) => `${formatMonth(m.month)} ${m.on_time_rate === null ? "no outcomes" : formatPercent(m.on_time_rate)} (${m.on_time} on time, ${m.late} late, ${m.overdue} overdue)`)
    .join("; ")}. Stated reliability ${formatPercent(statedReliability)}.`;

  return (
    <Card
      title="Monthly on-time trend"
      description="Orders by month of their promised date, with the observed on-time rate against the stated reliability"
      className={className}
      bodyClassName="flex flex-col"
      footer="The latest month is cut off at the as-of date; orders not yet due are not counted."
    >
      {months.length === 0 ? (
        <EmptyState icon={BarChart3} title="No delivery outcomes yet" />
      ) : (
        <>
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
              <span className="h-0.5 w-3 rounded" style={{ background: COLORS.rate }} /> Observed on-time rate
            </li>
            <li className="flex items-center gap-1.5">
              <span className="h-0 w-3 border-t-2 border-dashed" style={{ borderColor: COLORS.stated }} /> Stated reliability
            </li>
          </ul>
          <ChartFrame height={240} grow summary={summary}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={months} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 4" vertical={false} />
                <XAxis dataKey="month" tickFormatter={formatMonth} tick={AXIS_TICK} tickLine={false} axisLine={false} tickMargin={8} />
                <YAxis yAxisId="orders" tickFormatter={(v: number) => formatCompact(v)} tick={AXIS_TICK} tickLine={false} axisLine={false} width={40} />
                <YAxis yAxisId="rate" orientation="right" domain={[0, 1]} tickFormatter={(v: number) => formatPercent(v)} tick={AXIS_TICK} tickLine={false} axisLine={false} width={44} />
                <Tooltip
                  cursor={{ fill: "#eef0fb", opacity: 0.6 }}
                  content={({ active, payload }) => {
                    const m = payload?.[0]?.payload as SupplierDetail["monthly"][number] | undefined;
                    if (!active || !m) return null;
                    return (
                      <ChartTooltipCard
                        title={`Promised in ${formatMonth(m.month)}`}
                        rows={[
                          { label: "On time", value: formatInteger(m.on_time), color: COLORS.on_time },
                          { label: "Delivered late", value: formatInteger(m.late), color: COLORS.late },
                          { label: "Overdue", value: formatInteger(m.overdue), color: COLORS.overdue },
                          { label: "On-time rate", value: m.on_time_rate === null ? "—" : formatPercent(m.on_time_rate), color: COLORS.rate },
                        ]}
                      />
                    );
                  }}
                />
                <Bar yAxisId="orders" dataKey="on_time" stackId="outcome" fill={COLORS.on_time} maxBarSize={56} isAnimationActive={animate} />
                <Bar yAxisId="orders" dataKey="late" stackId="outcome" fill={COLORS.late} maxBarSize={56} isAnimationActive={animate} />
                <Bar yAxisId="orders" dataKey="overdue" stackId="outcome" fill={COLORS.overdue} radius={[3, 3, 0, 0]} maxBarSize={56} isAnimationActive={animate} />
                <ReferenceLine yAxisId="rate" y={statedReliability} stroke={COLORS.stated} strokeDasharray="5 4" strokeWidth={1.5} />
                <Line yAxisId="rate" type="monotone" dataKey="on_time_rate" stroke={COLORS.rate} strokeWidth={2} dot={{ r: 3, fill: COLORS.rate, strokeWidth: 0 }} connectNulls isAnimationActive={animate} />
              </ComposedChart>
            </ResponsiveContainer>
          </ChartFrame>
        </>
      )}
    </Card>
  );
}
