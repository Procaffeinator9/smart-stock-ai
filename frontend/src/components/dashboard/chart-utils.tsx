"use client";

import { useReducedMotion } from "motion/react";
import { useSyncExternalStore, type ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";

const noopSubscribe = () => () => {};

/** False during server rendering and hydration, true afterwards (charts need real DOM sizes). */
export function useHydrated(): boolean {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}

/** Chart animations follow the OS reduce-motion setting. */
export function useChartAnimation(): boolean {
  return !useReducedMotion();
}

// Category hues avoid the emerald/amber/red reserved for stock status.
const CATEGORY_PALETTE = ["#4f46e5", "#0ea5e9", "#8b5cf6", "#14b8a6", "#0369a1", "#d946ef", "#6366f1", "#94a3b8"];

export function categoryColor(categories: string[], category: string): string {
  const index = categories.indexOf(category);
  return CATEGORY_PALETTE[(index < 0 ? 0 : index) % CATEGORY_PALETTE.length];
}

interface ChartFrameProps {
  height: number;
  /** Grow to fill the remaining height of a flex-column parent, never shorter than `height`. */
  grow?: boolean;
  summary: string; // read by screen readers in place of the visual chart
  children: ReactNode;
  className?: string;
}

/** Chart container that shows a skeleton until the chart can render on the client. */
export function ChartFrame({ height, grow = false, summary, children, className }: ChartFrameProps) {
  const hydrated = useHydrated();
  return (
    <figure className={cn("relative", grow && "flex-1", className)} style={grow ? { minHeight: height } : { height }}>
      <figcaption className="sr-only">{summary}</figcaption>
      <div className="absolute inset-0">{hydrated ? children : <Skeleton className="size-full" />}</div>
    </figure>
  );
}

interface TooltipRow {
  label: string;
  value: string;
  color?: string;
}

export function ChartTooltipCard({ title, rows }: { title: string; rows: TooltipRow[] }) {
  return (
    <div className="min-w-40 rounded-xl border border-line bg-white/95 px-3 py-2.5 shadow-pop backdrop-blur">
      <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-subtle">{title}</p>
      <div className="space-y-1">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-4 text-[13px]">
            <span className="flex items-center gap-1.5 text-ink-muted">
              {row.color && <span className="size-2 rounded-full" style={{ background: row.color }} />}
              {row.label}
            </span>
            <span className="font-semibold tabular-nums text-ink">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export const AXIS_TICK = { fill: "#8591a7", fontSize: 11 };
export const GRID_STROKE = "#e5e9f0";
