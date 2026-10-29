"use client";

import { CalendarDays } from "lucide-react";

import { SegmentedControl } from "@/components/ui/segmented-control";
import { cn } from "@/lib/cn";
import { RANGE_OPTIONS } from "@/lib/dashboard/date-range";

import { useShell } from "./shell-context";

const OPTIONS = RANGE_OPTIONS.map((option) => ({ value: option.id, label: option.short, title: option.label }));

/**
 * Selects the window ending at the data's latest date. The exact live dates are shown on the
 * Overview cards (e.g. Sales trend), which come from the API rather than the static snapshot.
 */
export function DateRangeControl({ className }: { className?: string }) {
  const { range, setRange } = useShell();
  const selected = RANGE_OPTIONS.find((option) => option.id === range)!;

  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <span className="hidden items-center gap-1.5 text-xs text-ink-muted xl:flex">
        <CalendarDays aria-hidden className="size-3.5 text-ink-subtle" />
        {selected.label} of data
      </span>
      <SegmentedControl label="Date range" options={OPTIONS} value={range} onChange={setRange} />
    </div>
  );
}
