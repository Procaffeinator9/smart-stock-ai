// Chart points from the daily sales series, by day or by week (weeks start on Monday). No runtime
// imports, so the tests in frontend/tests can load this file directly.
import type { SalesDailySeries } from "./types";

export type Grain = "daily" | "weekly";

export interface TrendPoint {
  /** First and last day covered (equal for daily points). */
  start: string;
  end: string;
  /** Days covered; under 7 for a week cut off by the period's start or end. */
  days: number;
  revenue: number;
  units: number;
  gross_margin: number;
  promo_revenue: number;
}

const round2 = (value: number) => Math.round(value * 100) / 100;

function mondayOf(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
  return date.toISOString().slice(0, 10);
}

export function trendPoints(daily: SalesDailySeries, grain: Grain): TrendPoint[] {
  const points: TrendPoint[] = [];
  let weekStart: string | null = null;
  daily.dates.forEach((date, i) => {
    const week = grain === "weekly" ? mondayOf(date) : date;
    const last = points.at(-1);
    if (last && week === weekStart) {
      last.end = date;
      last.days += 1;
      last.revenue = round2(last.revenue + daily.revenue[i]);
      last.units += daily.units[i];
      last.gross_margin = round2(last.gross_margin + daily.gross_margin[i]);
      last.promo_revenue = round2(last.promo_revenue + daily.promo_revenue[i]);
    } else {
      weekStart = week;
      points.push({
        start: date,
        end: date,
        days: 1,
        revenue: daily.revenue[i],
        units: daily.units[i],
        gross_margin: daily.gross_margin[i],
        promo_revenue: daily.promo_revenue[i],
      });
    }
  });
  return points;
}
