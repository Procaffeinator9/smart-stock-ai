// Pure functions that derive view data from the snapshot for a selected date range.
import type { DailySeries } from "./types";

export interface DailyPoint {
  date: string;
  revenue: number;
  units: number;
}

/** The last `days` entries (clamped to what the dataset contains). */
export function lastDays<T>(values: T[], days: number): T[] {
  return values.slice(Math.max(0, values.length - days));
}

export function salesPoints(daily: DailySeries, days: number): DailyPoint[] {
  const start = Math.max(0, daily.dates.length - days);
  return daily.dates.slice(start).map((date, i) => ({
    date,
    revenue: daily.revenue[start + i],
    units: daily.units[start + i],
  }));
}

const sum = (values: number[]) => values.reduce((total, value) => total + value, 0);

export interface PeriodComparison {
  current: number;
  previous: number | null; // null when the dataset does not cover a full previous period
  change: number | null; // ratio, e.g. 0.042 for +4.2%
}

/** Total of `series` over the last `days`, compared with the `days` before that. */
export function comparePeriods(series: number[], days: number): PeriodComparison {
  const current = sum(lastDays(series, days));
  if (series.length < days * 2) return { current, previous: null, change: null };
  const previous = sum(series.slice(series.length - days * 2, series.length - days));
  return { current, previous, change: previous === 0 ? null : (current - previous) / previous };
}

export interface CategoryTotal {
  category: string;
  revenue: number;
  share: number;
}

export function categoryTotals(daily: DailySeries, days: number): CategoryTotal[] {
  const totals = Object.entries(daily.category_revenue).map(([category, series]) => ({
    category,
    revenue: sum(lastDays(series, days)),
  }));
  const grand = sum(totals.map((t) => t.revenue));
  return totals
    .map((t) => ({ ...t, share: grand === 0 ? 0 : t.revenue / grand }))
    .sort((a, b) => b.revenue - a.revenue);
}
