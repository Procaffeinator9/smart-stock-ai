import { CircleCheck, TriangleAlert } from "lucide-react";

import { cn } from "@/lib/cn";
import type { AttentionFlag } from "@/lib/suppliers/types";

/** "Needs attention" flags as small chips; the reason is the chip's tooltip (shown in full on the detail page). */
export function FlagChips({ flags, className }: { flags: AttentionFlag[]; className?: string }) {
  if (flags.length === 0) {
    return (
      <span className={cn("inline-flex items-center gap-1 text-xs text-emerald-700", className)}>
        <CircleCheck aria-hidden className="size-3.5" /> No flags
      </span>
    );
  }
  return (
    <ul className={cn("flex flex-wrap gap-1", className)} aria-label={`${flags.length} attention ${flags.length === 1 ? "flag" : "flags"}`}>
      {flags.map((flag) => (
        <li
          key={flag.code}
          title={flag.reason}
          className="inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800 ring-1 ring-inset ring-amber-600/20"
        >
          <TriangleAlert aria-hidden className="size-3" strokeWidth={2.25} />
          {flag.label}
        </li>
      ))}
    </ul>
  );
}

/** Every flag with its full reason (detail page). */
export function FlagList({ flags }: { flags: AttentionFlag[] }) {
  if (flags.length === 0) {
    return (
      <p className="flex items-center gap-2 rounded-xl bg-emerald-50/70 px-3 py-2.5 text-[13px] text-emerald-900 ring-1 ring-inset ring-emerald-600/15">
        <CircleCheck aria-hidden className="size-4 shrink-0" /> No &ldquo;Needs attention&rdquo; rule applies to this supplier.
      </p>
    );
  }
  return (
    <ul className="space-y-2">
      {flags.map((flag) => (
        <li
          key={flag.code}
          className="flex items-start gap-2 rounded-xl bg-amber-50/80 px-3 py-2.5 text-[13px] leading-5 text-amber-950 ring-1 ring-inset ring-amber-600/20"
        >
          <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-amber-700" />
          <span>
            <span className="font-semibold">{flag.label}.</span> {flag.reason}
          </span>
        </li>
      ))}
    </ul>
  );
}
