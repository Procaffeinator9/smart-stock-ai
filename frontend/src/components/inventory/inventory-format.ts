import { daysBetween, formatShortDate } from "@/lib/format";

/** "Overdue 3d" / "Today" / "Apr 4" for an expected delivery date, relative to the snapshot date. */
export function deliveryLabel(expected: string | null, asOf: string): { text: string; tone: string } | null {
  if (!expected) return null;
  const days = daysBetween(asOf, expected);
  if (days < 0) return { text: `Overdue ${-days}d`, tone: "text-red-700" };
  if (days === 0) return { text: "Due today", tone: "text-amber-700" };
  return { text: formatShortDate(expected), tone: "text-ink-muted" };
}

export function coverLabel(daysOfCover: number | null): string {
  return daysOfCover === null ? "—" : `${daysOfCover.toFixed(1)} d`;
}
