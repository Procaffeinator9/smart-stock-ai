"use client";

import { ScatterChart as ScatterIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS_TICK, ChartFrame, ChartTooltipCard, GRID_STROKE, useChartAnimation } from "@/components/dashboard/chart-utils";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { formatPercent } from "@/lib/format";
import { supplierLinks } from "@/lib/suppliers/query";
import type { SupplierScore } from "@/lib/suppliers/types";

import { formatDays, rateOrDash } from "./supplier-format";

const COLORS = { flagged: "#f59e0b", clear: "#4f46e5", stated: "#94a3b8" };

interface Point {
  id: string;
  name: string;
  lead: number;
  /** Plotted value: the observed rate, or the stated reliability for the hollow series. */
  y: number;
  observed: number;
  stated: number;
  sample: number;
  observedLead: number | null;
  flags: number;
}

/** Observed on-time rate (filled) and stated reliability (hollow) against each supplier's stated lead time. */
export function ReliabilityChart({ rows, className }: { rows: SupplierScore[]; className?: string }) {
  const router = useRouter();
  const animate = useChartAnimation();
  const points: Point[] = rows
    .filter((r) => r.on_time_rate !== null)
    .map((r) => ({
      id: r.supplier_id,
      name: r.supplier_name,
      lead: r.stated_lead_time_days,
      y: r.on_time_rate!,
      observed: r.on_time_rate!,
      stated: r.stated_reliability,
      sample: r.sample_size,
      observedLead: r.observed_lead_time_days,
      flags: r.flags.length,
    }));
  const flagged = points.filter((p) => p.flags > 0);
  const clear = points.filter((p) => p.flags === 0);
  const low = Math.max(0, Math.floor(Math.min(...points.flatMap((p) => [p.observed, p.stated]), 1) * 10) / 10 - 0.05);
  const summary = `Observed on-time rate against stated lead time: ${points
    .map((p) => `${p.name} ${formatPercent(p.observed)} (stated ${formatPercent(p.stated)}), ${p.lead}-day lead time`)
    .join("; ")}.`;

  const open = (point: unknown) => {
    const p = (point as { payload?: Point })?.payload;
    if (p?.id) router.push(supplierLinks(p.id, p.name).detail);
  };

  return (
    <Card
      title="Reliability vs lead time"
      description="Each supplier's observed on-time rate (filled) and stated reliability (hollow), by stated lead time. Select a point to open the supplier."
      className={className}
      footer={
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          <li className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-full" style={{ background: COLORS.clear }} /> Observed, no flags
          </li>
          <li className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-full" style={{ background: COLORS.flagged }} /> Observed, needs attention
          </li>
          <li className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-full border-2" style={{ borderColor: COLORS.stated }} /> Stated reliability
          </li>
        </ul>
      }
    >
      {points.length === 0 ? (
        <EmptyState icon={ScatterIcon} title="No delivery outcomes to plot" />
      ) : (
        <ChartFrame height={300} summary={summary}>
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 12, bottom: 16, left: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 4" />
              <XAxis
                type="number"
                dataKey="lead"
                name="Stated lead time"
                domain={[0, "dataMax + 1"]}
                allowDecimals={false}
                tick={AXIS_TICK}
                tickLine={false}
                axisLine={false}
                label={{ value: "Stated lead time (days)", position: "insideBottom", offset: -10, fill: "#8591a7", fontSize: 11 }}
              />
              <YAxis
                type="number"
                dataKey="y"
                domain={[low, 1]}
                tickFormatter={(v: number) => formatPercent(v)}
                tick={AXIS_TICK}
                tickLine={false}
                axisLine={false}
                width={48}
              />
              <Tooltip
                cursor={{ strokeDasharray: "3 3" }}
                content={({ active, payload }) => {
                  const p = payload?.[0]?.payload as Point | undefined;
                  if (!active || !p) return null;
                  return (
                    <ChartTooltipCard
                      title={p.name}
                      rows={[
                        { label: "Observed on time", value: `${rateOrDash(p.observed)} of ${p.sample}`, color: p.flags ? COLORS.flagged : COLORS.clear },
                        { label: "Stated reliability", value: formatPercent(p.stated), color: COLORS.stated },
                        { label: "Lead time", value: `stated ${p.lead} · observed ${p.observedLead === null ? "—" : formatDays(p.observedLead)}` },
                        { label: "Attention flags", value: String(p.flags) },
                      ]}
                    />
                  );
                }}
              />
              <Scatter
                name="Stated reliability"
                data={points.map((p) => ({ ...p, y: p.stated }))}
                fill="#fff"
                stroke={COLORS.stated}
                strokeWidth={2}
                isAnimationActive={animate}
                onClick={open}
                className="cursor-pointer"
              />
              <Scatter name="Observed, no flags" data={clear} fill={COLORS.clear} isAnimationActive={animate} onClick={open} className="cursor-pointer" />
              <Scatter name="Observed, needs attention" data={flagged} fill={COLORS.flagged} isAnimationActive={animate} onClick={open} className="cursor-pointer" />
            </ScatterChart>
          </ResponsiveContainer>
        </ChartFrame>
      )}
    </Card>
  );
}
