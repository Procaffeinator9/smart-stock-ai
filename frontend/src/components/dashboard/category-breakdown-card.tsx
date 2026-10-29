"use client";

import { PieChart as PieChartIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/cn";
import { categoryTotals, type CategoryTotal } from "@/lib/dashboard/selectors";
import type { DailySeries } from "@/lib/dashboard/types";
import { formatCurrency, formatCurrencyCompact, formatPercent } from "@/lib/format";

import { ChartFrame, ChartTooltipCard, categoryColor, useChartAnimation } from "./chart-utils";

interface CategoryBreakdownCardProps {
  daily: DailySeries;
  days: number;
  categories: string[];
  className?: string;
}

/** Overview: revenue share by category over the last `days` of the daily series. */
export function CategoryBreakdownCard({ daily, days, categories, className }: CategoryBreakdownCardProps) {
  return (
    <CategoryShareCard
      totals={categoryTotals(daily, days)}
      categories={categories}
      description={`Share of revenue, last ${days} days`}
      className={className}
    />
  );
}

interface CategoryShareCardProps {
  /** Sorted by revenue, largest first. */
  totals: CategoryTotal[];
  /** Every category in the dataset (keeps colours stable across pages and filters). */
  categories: string[];
  description: string;
  /** Optional extra text after each category's share, e.g. the change vs the previous period. */
  detail?: (category: string) => ReactNode;
  className?: string;
}

export function CategoryShareCard({ totals, categories, description, detail, className }: CategoryShareCardProps) {
  const [highlight, setHighlight] = useState<string | null>(null);
  const animate = useChartAnimation();
  const grand = totals.reduce((sum, t) => sum + t.revenue, 0);
  const summary = totals.map((t) => `${t.category} ${formatPercent(t.share)}`).join(", ");

  return (
    <Card title="Category breakdown" description={description} className={className}>
      {grand === 0 ? (
        <EmptyState icon={PieChartIcon} title="No revenue in this range" />
      ) : (
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center xl:flex-col xl:items-stretch">
          <ChartFrame height={190} summary={`Revenue share by category: ${summary}.`} className="mx-auto w-full max-w-[220px] shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Tooltip
                  content={({ active, payload }) =>
                    active && payload?.length ? (
                      <ChartTooltipCard
                        title={String(payload[0].name)}
                        rows={[
                          { label: "Revenue", value: formatCurrency(Number(payload[0].value)) },
                          { label: "Share", value: formatPercent(Number(payload[0].value) / grand) },
                        ]}
                      />
                    ) : null
                  }
                />
                <Pie
                  data={totals}
                  dataKey="revenue"
                  nameKey="category"
                  innerRadius="66%"
                  outerRadius="100%"
                  paddingAngle={1.5}
                  stroke="none"
                  isAnimationActive={animate}
                  animationDuration={800}
                >
                  {totals.map((t) => (
                    <Cell
                      key={t.category}
                      fill={categoryColor(categories, t.category)}
                      fillOpacity={highlight && highlight !== t.category ? 0.25 : 1}
                      style={{ transition: "fill-opacity 200ms" }}
                    />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div aria-hidden className="pointer-events-none absolute inset-0 grid place-items-center text-center">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-wide text-ink-subtle">Revenue</p>
                <p className="text-lg font-semibold tracking-tight text-ink">{formatCurrencyCompact(grand)}</p>
              </div>
            </div>
          </ChartFrame>

          <ul className="min-w-0 flex-1 space-y-1.5" onMouseLeave={() => setHighlight(null)}>
            {totals.map((t) => (
              <li
                key={t.category}
                onMouseEnter={() => setHighlight(t.category)}
                className={cn(
                  "grid grid-cols-[auto_1fr_auto] items-center gap-x-2.5 rounded-lg px-2 py-1 text-[13px] transition-opacity",
                  highlight && highlight !== t.category && "opacity-50",
                )}
              >
                <span className="size-2.5 rounded-full" style={{ background: categoryColor(categories, t.category) }} />
                <span className="truncate text-ink-muted">{t.category}</span>
                <span className="tabular-nums text-ink">
                  <span className="font-semibold">{formatPercent(t.share)}</span>
                  <span className="ml-2 text-xs text-ink-subtle">{formatCurrencyCompact(t.revenue)}</span>
                  {detail?.(t.category)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
