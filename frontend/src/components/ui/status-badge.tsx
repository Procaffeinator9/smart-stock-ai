import { CircleAlert, CircleCheck, Clock, PackageX, TriangleAlert, Truck, X, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";
import type { PositionStatus, PurchaseOrderStatus } from "@/lib/dashboard/types";

interface BadgeStyle {
  label: string;
  icon: LucideIcon;
  className: string;
}

// Colour is never the only signal: every badge has an icon and a text label.
export const POSITION_STATUS: Record<PositionStatus, BadgeStyle & { dot: string; bar: string }> = {
  healthy: {
    label: "Healthy",
    icon: CircleCheck,
    className: "bg-emerald-50 text-emerald-700 ring-emerald-600/15",
    dot: "bg-emerald-500",
    bar: "bg-emerald-500",
  },
  low: {
    label: "Low stock",
    icon: CircleAlert,
    className: "bg-amber-50 text-amber-800 ring-amber-600/20",
    dot: "bg-amber-500",
    bar: "bg-amber-400",
  },
  critical: {
    label: "Below safety",
    icon: TriangleAlert,
    className: "bg-red-50 text-red-700 ring-red-600/15",
    dot: "bg-red-500",
    bar: "bg-red-400",
  },
  out_of_stock: {
    label: "Out of stock",
    icon: PackageX,
    className: "bg-red-100 text-red-800 ring-red-700/20",
    dot: "bg-red-700",
    bar: "bg-red-700",
  },
};

// OPEN: on order on a past snapshot date, where placed vs in transit is not known.
export const PO_STATUS: Record<PurchaseOrderStatus | "OPEN", BadgeStyle> = {
  OPEN: { label: "On order", icon: Clock, className: "bg-slate-100 text-slate-700 ring-slate-500/15" },
  PLACED: { label: "Placed", icon: Clock, className: "bg-slate-100 text-slate-700 ring-slate-500/15" },
  IN_TRANSIT: { label: "In transit", icon: Truck, className: "bg-indigo-50 text-indigo-700 ring-indigo-600/15" },
  DELIVERED: { label: "Delivered", icon: CircleCheck, className: "bg-emerald-50 text-emerald-700 ring-emerald-600/15" },
  CANCELLED: { label: "Cancelled", icon: X, className: "bg-slate-50 text-slate-500 ring-slate-400/20" },
};

function Badge({ style, className }: { style: BadgeStyle; className?: string }) {
  const Icon = style.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        style.className,
        className,
      )}
    >
      <Icon aria-hidden className="size-3" strokeWidth={2.25} />
      {style.label}
    </span>
  );
}

export function StatusBadge({ status, className }: { status: PositionStatus; className?: string }) {
  return <Badge style={POSITION_STATUS[status]} className={className} />;
}

export function PurchaseOrderBadge({ status, className }: { status: PurchaseOrderStatus | "OPEN"; className?: string }) {
  return <Badge style={PO_STATUS[status]} className={className} />;
}
