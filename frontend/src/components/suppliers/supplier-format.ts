import { formatPercent } from "@/lib/format";
import type { SupplierScore } from "@/lib/suppliers/types";

export const rateOrDash = (value: number | null) => (value === null ? "—" : formatPercent(value));

export const formatDays = (value: number) => `${value.toFixed(1)} days`;

/** Observed lead time, and "stated N days · +x.x" for the gap (flagged when it is slipping). */
export function leadTimeText(row: Pick<SupplierScore, "observed_lead_time_days" | "stated_lead_time_days" | "lead_time_gap_days" | "flags">) {
  const gap = row.lead_time_gap_days;
  return {
    observed: row.observed_lead_time_days === null ? "—" : formatDays(row.observed_lead_time_days),
    detail: `stated ${row.stated_lead_time_days} days${gap === null ? "" : ` · ${gap >= 0 ? "+" : "−"}${Math.abs(gap).toFixed(1)}`}`,
    slipping: row.flags.some((f) => f.code === "lead_time_slip"),
  };
}
