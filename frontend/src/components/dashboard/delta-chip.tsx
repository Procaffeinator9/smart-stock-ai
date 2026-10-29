import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { cn } from "@/lib/cn";

interface DeltaChipProps {
  /** Signed change to display, already formatted, e.g. "+4.2%" or "−3". */
  text: string;
  direction: "up" | "down" | "flat";
  /** Whether "up" is good (revenue), bad (stockouts), or neither (inventory value). */
  goodWhen: "up" | "down" | "neutral";
  context?: string;
}

export function DeltaChip({ text, direction, goodWhen, context }: DeltaChipProps) {
  const tone =
    direction === "flat" || goodWhen === "neutral"
      ? "bg-slate-100 text-slate-700"
      : (direction === "up") === (goodWhen === "up")
        ? "bg-emerald-50 text-emerald-700"
        : "bg-red-50 text-red-700";
  const Icon = direction === "up" ? ArrowUpRight : direction === "down" ? ArrowDownRight : Minus;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-xs text-ink-subtle">
      <span className={cn("inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 font-semibold tabular-nums", tone)}>
        <Icon aria-hidden className="size-3.5" strokeWidth={2.4} />
        {text}
      </span>
      {context}
    </span>
  );
}

export function directionOf(change: number): "up" | "down" | "flat" {
  if (Math.abs(change) < 1e-9) return "flat";
  return change > 0 ? "up" : "down";
}

/** "+4.2%" / "−1.3%" using a true minus sign. */
export function signedPercent(ratio: number): string {
  const value = Math.abs(ratio * 100).toFixed(1);
  return `${ratio > 0 ? "+" : ratio < 0 ? "−" : ""}${value}%`;
}

export function signedNumber(value: number): string {
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toLocaleString("en-US")}`;
}
