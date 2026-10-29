import type { ReactNode } from "react";

import { directionOf, signedPercent } from "@/components/dashboard/delta-chip";
import { cn } from "@/lib/cn";

/** Rounded to the 0.1% shown, so a tiny change reads "0.0%" rather than "−0.0%". */
export function roundedChange(change: number): number {
  return Math.round(change * 1000) / 1000;
}

/** "+4.2%" in green or "−3.1%" in red (revenue-style: up is good); `fallback` when there is no comparison. */
export function ChangeText({ change, className, fallback = null }: { change: number | null; className?: string; fallback?: ReactNode }) {
  if (change === null) return fallback;
  const rounded = roundedChange(change);
  const direction = directionOf(rounded);
  return (
    <span
      className={cn(
        "font-medium tabular-nums",
        direction === "up" ? "text-emerald-700" : direction === "down" ? "text-red-700" : "text-ink-subtle",
        className,
      )}
    >
      {signedPercent(rounded)}
    </span>
  );
}
