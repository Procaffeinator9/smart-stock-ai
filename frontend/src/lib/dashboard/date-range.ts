export const RANGE_OPTIONS = [
  { id: "7d", days: 7, short: "7D", label: "Last 7 days" },
  { id: "30d", days: 30, short: "30D", label: "Last 30 days" },
  { id: "90d", days: 90, short: "90D", label: "Last 90 days" },
] as const;

export type RangeId = (typeof RANGE_OPTIONS)[number]["id"];

export const DEFAULT_RANGE: RangeId = "30d";

export function rangeDays(id: RangeId): number {
  return RANGE_OPTIONS.find((option) => option.id === id)!.days;
}
