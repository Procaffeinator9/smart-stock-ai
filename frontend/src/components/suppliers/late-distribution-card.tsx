"use client";

import { Timer } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS_TICK, ChartFrame, ChartTooltipCard, GRID_STROKE, useChartAnimation } from "@/components/dashboard/chart-utils";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { formatInteger, formatPercent } from "@/lib/format";
import type { SupplierDetail } from "@/lib/suppliers/types";

interface LateDistributionCardProps {
  buckets: SupplierDetail["late_distribution"];
  overdue: number;
  className?: string;
}

/** Delivered orders by days late (on time first). */
export function LateDistributionCard({ buckets, overdue, className }: LateDistributionCardProps) {
  const animate = useChartAnimation();
  const delivered = buckets.reduce((sum, b) => sum + b.orders, 0);
  const summary = `Delivered orders by days late: ${buckets.map((b) => `${b.label} ${b.orders}`).join(", ")}.`;

  return (
    <Card
      title="Late deliveries"
      description="Delivered orders by days after the promised date"
      className={className}
      bodyClassName="flex flex-col"
      footer={`${formatInteger(delivered)} delivered orders. ${formatInteger(overdue)} open ${overdue === 1 ? "order is" : "orders are"} overdue and not shown here.`}
    >
      {delivered === 0 ? (
        <EmptyState icon={Timer} title="No deliveries yet" />
      ) : (
        <ChartFrame height={240} grow summary={summary}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={buckets} margin={{ top: 6, right: 4, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 4" vertical={false} />
              <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} interval={0} tickMargin={8} />
              <YAxis allowDecimals={false} tick={AXIS_TICK} tickLine={false} axisLine={false} width={36} />
              <Tooltip
                cursor={{ fill: "#eef0fb", opacity: 0.6 }}
                content={({ active, payload }) => {
                  const b = payload?.[0]?.payload as SupplierDetail["late_distribution"][number] | undefined;
                  if (!active || !b) return null;
                  return (
                    <ChartTooltipCard
                      title={b.min_days === 0 ? "Delivered on time" : `Delivered ${b.label} late`}
                      rows={[
                        { label: "Orders", value: formatInteger(b.orders) },
                        { label: "Share of deliveries", value: formatPercent(b.orders / delivered) },
                      ]}
                    />
                  );
                }}
              />
              <Bar dataKey="orders" radius={[3, 3, 0, 0]} isAnimationActive={animate}>
                {buckets.map((b) => (
                  <Cell key={b.label} fill={b.min_days === 0 ? "#10b981" : "#f59e0b"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      )}
    </Card>
  );
}
