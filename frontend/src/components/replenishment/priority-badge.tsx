import { CircleAlert, Eye, Hourglass, PackagePlus, Siren, TriangleAlert, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";
import type { Action, Priority } from "@/lib/replenishment/types";

// Colour is never the only signal: every badge has an icon and a text label.
export const PRIORITY_STYLE: Record<Priority, { label: string; icon: LucideIcon; className: string; dot: string }> = {
  critical: { label: "Critical", icon: Siren, className: "bg-red-100 text-red-800 ring-red-700/20", dot: "bg-red-600" },
  high: { label: "High", icon: TriangleAlert, className: "bg-orange-50 text-orange-800 ring-orange-600/20", dot: "bg-orange-500" },
  medium: { label: "Medium", icon: CircleAlert, className: "bg-amber-50 text-amber-800 ring-amber-600/20", dot: "bg-amber-400" },
  low: { label: "Low", icon: Eye, className: "bg-slate-100 text-slate-700 ring-slate-500/15", dot: "bg-slate-400" },
};

export const ACTION_STYLE: Record<Action, { label: string; icon: LucideIcon }> = {
  order: { label: "Order now", icon: PackagePlus },
  expedite: { label: "Expedite", icon: Hourglass },
  watch: { label: "Watch", icon: Eye },
};

export function PriorityBadge({ priority, className }: { priority: Priority; className?: string }) {
  const style = PRIORITY_STYLE[priority];
  const Icon = style.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset", style.className, className)}>
      <Icon aria-hidden className="size-3" strokeWidth={2.25} />
      {style.label}
    </span>
  );
}

export function ActionLabel({ action, className }: { action: Action; className?: string }) {
  const style = ACTION_STYLE[action];
  const Icon = style.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap text-[11px] font-medium text-ink-muted", className)}>
      <Icon aria-hidden className="size-3" />
      {style.label}
    </span>
  );
}
